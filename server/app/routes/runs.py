"""Command-run ingestion and retrieval API routes."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas.pagination import PaginatedResponse
from app.schemas.run import RunCreate, RunResponse
from app.schemas import ResponseEnvelope
from app.services import run_service

router = APIRouter(prefix="/runs", tags=["Command Runs"])


@router.post(
    "",
    response_model=ResponseEnvelope[RunResponse],
    summary="Ingest a command execution run event",
)
async def ingest_run_endpoint(
    payload: RunCreate,
    response: Response,
    db: Database = Depends(get_database),
):
    run, is_new = run_service.ingest_run(db, payload)
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return ResponseEnvelope[RunResponse](success=True, data=run, error=None)


@router.get(
    "",
    response_model=ResponseEnvelope[PaginatedResponse[RunResponse]],
    summary="List command execution runs (all or filtered by project)",
)
async def list_runs_endpoint(
    project_id: Optional[str] = Query(default=None, description="Filter by project ID"),
    status: Optional[str] = Query(default=None, description="Filter by status (success/failure)"),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    db: Database = Depends(get_database),
):
    runs = run_service.list_runs(
        db, project_id=project_id, limit=limit, skip=skip, status_filter=status
    )
    return ResponseEnvelope[PaginatedResponse[RunResponse]](success=True, data=runs, error=None)



@router.get(
    "/{event_id}",
    response_model=ResponseEnvelope[RunResponse],
    summary="Get command run by event ID",
)
async def get_run_endpoint(
    event_id: str,
    db: Database = Depends(get_database),
):
    run = run_service.get_run(db, event_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with event_id '{event_id}' not found.",
        )
    return ResponseEnvelope[RunResponse](success=True, data=run, error=None)
