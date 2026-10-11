"""Performance measurement persistence, baselines, and analytics API routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response, status
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas.pagination import PaginatedResponse
from app.schemas.performance import (
    BaselineCalculationRequest,
    PerformanceAnalyticsResponse,
    PerformanceBaselineResponse,
    PerformanceMeasurementCreate,
    PerformanceMeasurementResponse,
)
from app.schemas import ResponseEnvelope
from app.services import performance_service

router = APIRouter(tags=["Performance"])


@router.post(
    "/performance",
    response_model=ResponseEnvelope[PerformanceMeasurementResponse],
    summary="Record a command execution performance measurement",
)
async def record_performance_endpoint(
    payload: PerformanceMeasurementCreate,
    response: Response,
    db: Database = Depends(get_database),
):
    """Record a performance measurement with idempotency, conflict detection, and regression analysis."""
    measurement, is_new = performance_service.record_performance_measurement(db, payload)
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return ResponseEnvelope[PerformanceMeasurementResponse](success=True, data=measurement, error=None)


@router.post(
    "/projects/{project_id}/performance/baseline",
    response_model=ResponseEnvelope[PerformanceBaselineResponse],
    summary="Calculate and establish performance baseline for comparable commands",
)
async def calculate_baseline_endpoint(
    project_id: str,
    payload: Optional[BaselineCalculationRequest] = None,
    command_signature: Optional[str] = Query(default=None, description="Optional command signature"),
    db: Database = Depends(get_database),
):
    """Calculate a robust median baseline for successful runs of comparable commands."""
    target_sig = payload.command_signature if (payload and payload.command_signature) else command_signature
    min_samples = payload.min_samples if (payload and payload.min_samples) else None
    baseline = performance_service.calculate_baseline(
        db,
        project_id=project_id,
        command_signature=target_sig,
        min_samples=min_samples,
    )
    return ResponseEnvelope[PerformanceBaselineResponse](success=True, data=baseline, error=None)


@router.get(
    "/projects/{project_id}/performance/baselines",
    response_model=ResponseEnvelope[List[PerformanceBaselineResponse]],
    summary="List established baselines for a project",
)
async def get_project_baselines_endpoint(
    project_id: str,
    command_signature: Optional[str] = Query(default=None, description="Filter by command signature"),
    db: Database = Depends(get_database),
):
    """Retrieve established performance baselines for a project."""
    baselines = performance_service.get_project_baselines(
        db, project_id=project_id, command_signature=command_signature
    )
    return ResponseEnvelope[List[PerformanceBaselineResponse]](success=True, data=baselines, error=None)


@router.get(
    "/projects/{project_id}/performance",
    response_model=ResponseEnvelope[PaginatedResponse[PerformanceMeasurementResponse]],
    summary="Retrieve performance measurement history for a project",
)
async def list_performance_history_endpoint(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    command_signature: Optional[str] = Query(default=None, description="Filter by command signature"),
    regression_status: Optional[str] = Query(
        default=None, description="Filter by regression status (unknown, normal, potential_regression)"
    ),
    db: Database = Depends(get_database),
):
    """List paginated performance measurements, newest first."""
    history = performance_service.list_performance_history(
        db,
        project_id=project_id,
        limit=limit,
        skip=skip,
        command_signature=command_signature,
        regression_status=regression_status,
    )
    return ResponseEnvelope[PaginatedResponse[PerformanceMeasurementResponse]](
        success=True, data=history, error=None
    )


@router.get(
    "/projects/{project_id}/performance/analytics",
    response_model=ResponseEnvelope[PerformanceAnalyticsResponse],
    summary="Get project performance summary and command-grouped metrics",
)
async def get_performance_analytics_endpoint(
    project_id: str,
    db: Database = Depends(get_database),
):
    """Aggregate performance metrics, distributions, and baseline comparisons for a project."""
    analytics = performance_service.get_performance_analytics(db, project_id=project_id)
    return ResponseEnvelope[PerformanceAnalyticsResponse](success=True, data=analytics, error=None)
