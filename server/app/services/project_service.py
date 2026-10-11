"""Service layer for project registration and management."""

import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from fastapi import HTTPException, status
from pymongo import DESCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.schemas.pagination import PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectResponse


def _generate_project_id(name: str) -> str:
    """Generate a readable project identifier slug."""
    clean_name = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    if not clean_name:
        clean_name = "project"
    return f"proj_{clean_name[:24]}_{uuid4().hex[:6]}"


def create_project(db: Database, payload: ProjectCreate) -> ProjectResponse:
    """Register a new project with unique identifier enforcement."""
    project_id = payload.project_id or _generate_project_id(payload.name)
    now = datetime.now(timezone.utc)

    doc = {
        "project_id": project_id,
        "name": payload.name,
        "language": payload.language,
        "settings": payload.settings or {},
        "created_at": now,
        "updated_at": now,
    }

    try:
        db.projects.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project with ID '{project_id}' already exists.",
        )

    return ProjectResponse(
        project_id=project_id,
        name=payload.name,
        language=payload.language,
        settings=payload.settings or {},
        created_at=now,
        updated_at=now,
    )


def get_project(db: Database, project_id: str) -> Optional[ProjectResponse]:
    """Retrieve a project by its unique ID enriched with operational metrics."""
    doc = db.projects.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        return None

    # Calculate actual project metrics from command_runs, incidents, and fix_outcomes
    total_runs = db.command_runs.count_documents({"project_id": project_id})
    failures = db.command_runs.count_documents({"project_id": project_id, "exit_code": {"$ne": 0}})
    verified_fixes = db.fix_outcomes.count_documents({"project_id": project_id, "status": "verified"})

    last_run = db.command_runs.find_one(
        {"project_id": project_id},
        sort=[("started_at", DESCENDING)],
    )
    last_run_at = last_run.get("started_at") if last_run else None
    last_run_status = (
        "failure" if (last_run and last_run.get("exit_code") != 0)
        else ("success" if last_run else "unknown")
    )

    durations = [
        d["duration_ms"]
        for d in db.command_runs.find(
            {"project_id": project_id, "duration_ms": {"$exists": True, "$ne": None}},
            {"duration_ms": 1, "_id": 0},
        )
    ]
    durations.sort()
    median_dur = durations[len(durations) // 2] if durations else None

    doc["total_runs"] = total_runs
    doc["failure_count"] = failures
    doc["verified_fix_count"] = verified_fixes
    doc["median_duration_ms"] = median_dur
    doc["last_run_at"] = last_run_at
    doc["last_run_status"] = last_run_status

    return ProjectResponse(**doc)


def list_projects(db: Database, limit: int = 50, skip: int = 0) -> PaginatedResponse[ProjectResponse]:
    """Retrieve paginated list of registered projects sorted newest first with enriched metrics."""
    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    total = db.projects.count_documents({})
    cursor = list(db.projects.find({}, {"_id": 0}).sort("created_at", DESCENDING).skip(skip).limit(limit))

    if not cursor:
        return PaginatedResponse[ProjectResponse](items=[], total=total, limit=limit, skip=skip)

    # Batch compute metrics for retrieved projects
    project_ids = [d["project_id"] for d in cursor]
    run_stats_pipe = [
        {"$match": {"project_id": {"$in": project_ids}}},
        {
            "$group": {
                "_id": "$project_id",
                "total_runs": {"$sum": 1},
                "failures": {"$sum": {"$cond": [{"$ne": ["$exit_code", 0]}, 1, 0]}},
                "last_run_at": {"$max": "$started_at"},
                "durations": {"$push": "$duration_ms"},
            }
        },
    ]
    run_stats = {r["_id"]: r for r in db.command_runs.aggregate(run_stats_pipe)}

    fix_stats_pipe = [
        {"$match": {"project_id": {"$in": project_ids}, "status": "verified"}},
        {"$group": {"_id": "$project_id", "verified_fixes": {"$sum": 1}}},
    ]
    fix_stats = {r["_id"]: r["verified_fixes"] for r in db.fix_outcomes.aggregate(fix_stats_pipe)}

    items = []
    for d in cursor:
        pid = d["project_id"]
        r_stat = run_stats.get(pid, {})
        durs = [x for x in r_stat.get("durations", []) if x is not None]
        durs.sort()
        d["total_runs"] = r_stat.get("total_runs", 0)
        d["failure_count"] = r_stat.get("failures", 0)
        d["verified_fix_count"] = fix_stats.get(pid, 0)
        d["median_duration_ms"] = durs[len(durs) // 2] if durs else None
        d["last_run_at"] = r_stat.get("last_run_at")
        d["last_run_status"] = (
            "failure" if d["failure_count"] > 0
            else ("success" if d["total_runs"] > 0 else "unknown")
        )
        items.append(ProjectResponse(**d))

    return PaginatedResponse[ProjectResponse](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )
