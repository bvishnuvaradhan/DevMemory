"""Service layer for command-run ingestion, duplicate prevention, and retrieval."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from pymongo import DESCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.schemas.pagination import PaginatedResponse
from app.schemas.run import RunCreate, RunResponse
from app.services.incident_service import create_or_get_incident


def ingest_run(db: Database, payload: RunCreate) -> tuple[RunResponse, bool]:
    """Ingest a command execution run with idempotent duplicate handling and incident creation.

    Returns:
        (RunResponse, is_new: bool)
    """
    # 1. Verify referenced project exists
    project = db.projects.find_one({"project_id": payload.project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{payload.project_id}' not found.",
        )

    now = datetime.now(timezone.utc)
    started_at = payload.started_at or now
    finished_at = payload.finished_at or (started_at + timedelta(milliseconds=payload.duration_ms))
    run_status = "success" if payload.exit_code == 0 else "failure"

    # 2. Check and derive incident if error occurred
    incident_id: Optional[str] = None
    if payload.exit_code != 0:
        if payload.error_context and (payload.error_context.error_type or payload.error_context.message):
            ctx = payload.error_context
            inc = create_or_get_incident(
                db=db,
                project_id=payload.project_id,
                event_id=payload.event_id,
                error_type=ctx.error_type or "CommandError",
                error_message=ctx.message or payload.stderr or "Unknown command failure",
                file_path=ctx.file_path,
                line=ctx.line,
                column=ctx.column,
                source_snippet=ctx.snippet,
            )
            incident_id = inc.incident_id
        else:
            # Fallback incident derivation for non-zero exit code without structured context
            first_err = (payload.stderr or payload.stdout or "").strip().splitlines()
            err_msg = first_err[0][:1000] if first_err else f"Command failed with exit code {payload.exit_code}"
            inc = create_or_get_incident(
                db=db,
                project_id=payload.project_id,
                event_id=payload.event_id,
                error_type="CommandError",
                error_message=err_msg,
                file_path=None,
                line=None,
                column=None,
                source_snippet=None,
            )
            incident_id = inc.incident_id

    doc = {
        "event_id": payload.event_id,
        "project_id": payload.project_id,
        "command": payload.command,
        "exit_code": payload.exit_code,
        "status": run_status,
        "duration_ms": payload.duration_ms,
        "stdout": payload.stdout or "",
        "stderr": payload.stderr or "",
        "started_at": started_at,
        "finished_at": finished_at,
        "created_at": now,
        "environment": payload.environment.model_dump() if payload.environment else None,
        "error_context": payload.error_context.model_dump() if payload.error_context else None,
        "incident_id": incident_id,
    }

    # 3. Race-safe atomic insert with conflict detection
    try:
        db.command_runs.insert_one(doc)
    except DuplicateKeyError:
        # Existing run with same event_id
        existing = db.command_runs.find_one({"event_id": payload.event_id}, {"_id": 0})
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Race condition encountered during run ingestion.",
            )

        # Detect conflicting payload under identical event_id
        if (
            existing["command"] != payload.command
            or existing["project_id"] != payload.project_id
            or existing["exit_code"] != payload.exit_code
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Conflict: event_id '{payload.event_id}' already exists with a different payload "
                    f"(stored project '{existing['project_id']}', command '{existing['command']}')."
                ),
            )

        # Idempotent retry: return existing run
        resp = RunResponse(**existing)
        resp.idempotent = True
        return resp, False

    resp = RunResponse(**doc)
    resp.idempotent = False
    return resp, True


def get_run(db: Database, event_id: str) -> Optional[RunResponse]:
    """Retrieve a run record by its unique event ID."""
    doc = db.command_runs.find_one({"event_id": event_id}, {"_id": 0})
    if not doc:
        return None
    return RunResponse(**doc)


def list_project_runs(
    db: Database,
    project_id: str,
    limit: int = 50,
    skip: int = 0,
    status_filter: Optional[str] = None,
) -> PaginatedResponse[RunResponse]:
    """Retrieve paginated runs for a project sorted newest first."""
    # Verify project exists
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    filter_query: dict = {"project_id": project_id}
    if status_filter:
        norm_status = status_filter.strip().lower()
        if norm_status in ("success", "ok", "0"):
            filter_query["exit_code"] = 0
        elif norm_status in ("failure", "failed", "error", "1"):
            filter_query["exit_code"] = {"$ne": 0}

    total = db.command_runs.count_documents(filter_query)
    cursor = (
        db.command_runs.find(filter_query, {"_id": 0})
        .sort("started_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    items = [RunResponse(**d) for d in cursor]

    return PaginatedResponse[RunResponse](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )
