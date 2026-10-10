"""Analytics and telemetry audit event routes."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas import ResponseEnvelope
from app.services import analytics_service

router = APIRouter(tags=["Analytics & Events"])


@router.get(
    "/analytics/overview",
    response_model=ResponseEnvelope[Dict[str, Any]],
    summary="Get platform-wide aggregated telemetry and health overview",
)
def get_platform_overview_endpoint(
    db: Database = Depends(get_database),
):
    overview = analytics_service.get_global_overview(db)
    return ResponseEnvelope[Dict[str, Any]](success=True, data=overview, error=None)


@router.get(
    "/analytics/performance",
    response_model=ResponseEnvelope[Dict[str, Any]],
    summary="Get platform-wide performance trend and project distributions",
)
def get_performance_overview_endpoint(
    db: Database = Depends(get_database),
):
    overview = analytics_service.get_global_overview(db)
    perf_data = {
        "trend": overview.get("performanceTrend", []),
        "byProject": {},
    }
    return ResponseEnvelope[Dict[str, Any]](success=True, data=perf_data, error=None)


@router.get(
    "/events",
    response_model=ResponseEnvelope[List[Dict[str, Any]]],
    summary="List chronologically sorted global audit events",
)
def list_global_events_endpoint(
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    db: Database = Depends(get_database),
):
    events = analytics_service.get_events(db, project_id=None, limit=limit, skip=skip)
    return ResponseEnvelope[List[Dict[str, Any]]](success=True, data=events, error=None)


@router.get(
    "/projects/{project_id}/events",
    response_model=ResponseEnvelope[List[Dict[str, Any]]],
    summary="List chronologically sorted audit events for a project",
)
def list_project_events_endpoint(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    db: Database = Depends(get_database),
):
    events = analytics_service.get_events(db, project_id=project_id, limit=limit, skip=skip)
    return ResponseEnvelope[List[Dict[str, Any]]](success=True, data=events, error=None)
