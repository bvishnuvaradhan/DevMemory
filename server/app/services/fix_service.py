"""Service layer for fix outcome lifecycle tracking and evidence verification."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from fastapi import HTTPException, status
from pymongo import DESCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.schemas.fix import FixOutcomeCreate, FixOutcomeResponse, FixOutcomeUpdate
from app.schemas.pagination import PaginatedResponse

# Valid status transitions state machine
ALLOWED_TRANSITIONS = {
    "proposed": {"applied", "verifying", "failed", "reverted"},
    "applied": {"verifying", "failed", "reverted"},
    "verifying": {"verified", "failed", "reverted"},
    "verified": {"reverted", "failed"},
    "failed": {"verifying", "proposed", "reverted"},
    "reverted": {"proposed", "verifying"},
}


def create_fix(
    db: Database,
    incident_id: str,
    payload: FixOutcomeCreate,
) -> FixOutcomeResponse:
    """Register a proposed fix for an existing incident."""
    incident = db.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    project_id = incident["project_id"]
    fix_id = payload.fix_id or f"fix_{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    doc = {
        "fix_id": fix_id,
        "incident_id": incident_id,
        "project_id": project_id,
        "description": payload.description,
        "status": "proposed",
        "verification_method": None,
        "verification_command": None,
        "verification_exit_code": None,
        "verification_details": None,
        "verification_source": None,
        "verified_at": None,
        "created_at": now,
        "updated_at": now,
    }

    try:
        db.fix_outcomes.insert_one(doc)
    except DuplicateKeyError:
        existing = db.fix_outcomes.find_one({"fix_id": fix_id}, {"_id": 0})
        if existing:
            return FixOutcomeResponse(**existing)
        raise

    return FixOutcomeResponse(**doc)


def get_fix(db: Database, fix_id: str) -> Optional[FixOutcomeResponse]:
    """Retrieve a single fix outcome record by its ID."""
    doc = db.fix_outcomes.find_one({"fix_id": fix_id}, {"_id": 0})
    if not doc:
        return None
    return FixOutcomeResponse(**doc)


def update_fix(
    db: Database,
    fix_id: str,
    payload: FixOutcomeUpdate,
) -> FixOutcomeResponse:
    """Update fix outcome status and verification metadata adhering to evidence validation rules."""
    existing = db.fix_outcomes.find_one({"fix_id": fix_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fix with ID '{fix_id}' not found.",
        )

    current_status = existing["status"]
    target_status = payload.status or current_status

    # 1. Enforce status transition policy
    if target_status != current_status:
        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Invalid status transition from '{current_status}' to '{target_status}'. "
                    f"Allowed transitions: {sorted(list(allowed))}."
                ),
            )

    # 2. Strict Verification Evidence Rule:
    # A fix may only be marked 'verified' if supported by concrete recorded evidence:
    # Option A: Command-based verification (command executed and exit_code == 0)
    # Option B: Explicit user confirmation with recorded confirmation details
    verified_at = existing.get("verified_at")
    if target_status == "verified":
        cmd = payload.verification_command or existing.get("verification_command")
        exit_code = (
            payload.verification_exit_code
            if payload.verification_exit_code is not None
            else existing.get("verification_exit_code")
        )
        source = (
            payload.verification_source
            or existing.get("verification_source")
            or ""
        ).strip().lower()
        method = (
            payload.verification_method
            or existing.get("verification_method")
            or ""
        ).strip().lower()
        details = (
            payload.verification_details
            or existing.get("verification_details")
            or ""
        ).strip()

        has_command_evidence = (
            cmd is not None and len(cmd.strip()) > 0 and exit_code == 0
        )
        has_user_evidence = (
            source == "user_confirmation" or method == "user_confirmation"
        ) and len(details) > 0

        if not (has_command_evidence or has_user_evidence):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cannot mark fix as verified without supporting verification evidence. "
                    "Provide either automated execution evidence (command with exit_code=0) "
                    "or explicit user confirmation with verification details."
                ),
            )

        verified_at = datetime.now(timezone.utc)
    elif target_status in ("reverted", "failed", "proposed"):
        # Reset verified_at if fix is reverted, failed, or reset
        verified_at = None

    now = datetime.now(timezone.utc)
    update_fields = {"updated_at": now}

    if payload.status is not None:
        update_fields["status"] = target_status
    if payload.description is not None:
        update_fields["description"] = payload.description
    if payload.verification_method is not None:
        update_fields["verification_method"] = payload.verification_method
    if payload.verification_command is not None:
        update_fields["verification_command"] = payload.verification_command
    if payload.verification_exit_code is not None:
        update_fields["verification_exit_code"] = payload.verification_exit_code
    if payload.verification_details is not None:
        update_fields["verification_details"] = payload.verification_details
    if payload.verification_source is not None:
        update_fields["verification_source"] = payload.verification_source

    update_fields["verified_at"] = verified_at

    db.fix_outcomes.update_one({"fix_id": fix_id}, {"$set": update_fields})

    updated_doc = db.fix_outcomes.find_one({"fix_id": fix_id}, {"_id": 0})
    return FixOutcomeResponse(**updated_doc)


def list_incident_fixes(
    db: Database,
    incident_id: str,
    limit: int = 50,
    skip: int = 0,
) -> PaginatedResponse[FixOutcomeResponse]:
    """Retrieve paginated fixes for a specific incident sorted newest first."""
    incident = db.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    filter_query = {"incident_id": incident_id}
    total = db.fix_outcomes.count_documents(filter_query)
    cursor = (
        db.fix_outcomes.find(filter_query, {"_id": 0})
        .sort("created_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    items = [FixOutcomeResponse(**d) for d in cursor]

    return PaginatedResponse[FixOutcomeResponse](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )
