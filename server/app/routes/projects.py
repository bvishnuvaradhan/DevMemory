"""Project registration, retrieval, history, and analytics API routes."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas.analytics import ProjectAnalyticsResponse, RecurringErrorsResponse
from app.schemas.incident import IncidentResponse
from app.schemas.pagination import PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectResponse
from app.schemas.run import RunResponse
from app.schemas import ResponseEnvelope
from app.services import analytics_service, incident_service, project_service, run_service

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=ResponseEnvelope[ProjectResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new project",
)
async def create_project_endpoint(
    payload: ProjectCreate,
    db: Database = Depends(get_database),
):
    project = project_service.create_project(db, payload)
    return ResponseEnvelope[ProjectResponse](success=True, data=project, error=None)


@router.get(
    "",
    response_model=ResponseEnvelope[PaginatedResponse[ProjectResponse]],
    summary="List registered projects",
)
async def list_projects_endpoint(
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    db: Database = Depends(get_database),
):
    projects = project_service.list_projects(db, limit=limit, skip=skip)
    return ResponseEnvelope[PaginatedResponse[ProjectResponse]](success=True, data=projects, error=None)


@router.get(
    "/{project_id}",
    response_model=ResponseEnvelope[ProjectResponse],
    summary="Get project details by ID",
)
async def get_project_endpoint(
    project_id: str,
    db: Database = Depends(get_database),
):
    project = project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )
    return ResponseEnvelope[ProjectResponse](success=True, data=project, error=None)


@router.get(
    "/{project_id}/runs",
    response_model=ResponseEnvelope[PaginatedResponse[RunResponse]],
    summary="List runs for a specific project",
)
async def list_project_runs_endpoint(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None, description="Filter by 'success' or 'failure'"),
    db: Database = Depends(get_database),
):
    runs = run_service.list_project_runs(
        db, project_id=project_id, limit=limit, skip=skip, status_filter=status
    )
    return ResponseEnvelope[PaginatedResponse[RunResponse]](success=True, data=runs, error=None)


@router.get(
    "/{project_id}/incidents",
    response_model=ResponseEnvelope[PaginatedResponse[IncidentResponse]],
    summary="List incidents for a specific project",
)
async def list_project_incidents_endpoint(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    db: Database = Depends(get_database),
):
    incidents = incident_service.list_project_incidents(
        db, project_id=project_id, limit=limit, skip=skip
    )
    return ResponseEnvelope[PaginatedResponse[IncidentResponse]](success=True, data=incidents, error=None)


@router.get(
    "/{project_id}/analytics/recurring",
    response_model=ResponseEnvelope[RecurringErrorsResponse],
    summary="Aggregate and rank recurring errors for a project",
)
async def get_recurring_errors_endpoint(
    project_id: str,
    limit: int = Query(default=10, ge=1, le=50, description="Max number of recurring error groups"),
    db: Database = Depends(get_database),
):
    recurring = analytics_service.get_recurring_errors(db, project_id=project_id, limit=limit)
    return ResponseEnvelope[RecurringErrorsResponse](success=True, data=recurring, error=None)


@router.get(
    "/{project_id}/analytics",
    response_model=ResponseEnvelope[ProjectAnalyticsResponse],
    summary="Get summary metrics and health overview for a project",
)
async def get_project_analytics_endpoint(
    project_id: str,
    db: Database = Depends(get_database),
):
    analytics = analytics_service.get_project_analytics(db, project_id=project_id)
    return ResponseEnvelope[ProjectAnalyticsResponse](success=True, data=analytics, error=None)
