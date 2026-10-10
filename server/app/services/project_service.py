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
    """Retrieve a project by its unique ID."""
    doc = db.projects.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        return None
    return ProjectResponse(**doc)


def list_projects(db: Database, limit: int = 50, skip: int = 0) -> PaginatedResponse[ProjectResponse]:
    """Retrieve paginated list of registered projects sorted newest first."""
    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    total = db.projects.count_documents({})
    cursor = db.projects.find({}, {"_id": 0}).sort("created_at", DESCENDING).skip(skip).limit(limit)
    items = [ProjectResponse(**d) for d in cursor]

    return PaginatedResponse[ProjectResponse](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )
