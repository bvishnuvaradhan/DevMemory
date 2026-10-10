"""Health check endpoints for application and database status."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from app.db.mongo import mongo_manager
from app.schemas import HealthData, ResponseEnvelope

router = APIRouter(tags=["Health"])


def get_db_health() -> bool:
    """Dependency that pings MongoDB and returns boolean health status."""
    return mongo_manager.ping()


@router.get(
    "/health",
    response_model=ResponseEnvelope[HealthData],
    summary="Check application and database health status",
    responses={
        200: {"description": "Application and database are healthy"},
        503: {"description": "Database service is unavailable"},
    },
)
async def check_health(
    db_healthy: bool = Depends(get_db_health),
):
    """Return health status distinguishing application and database health."""
    if db_healthy:
        return ResponseEnvelope[HealthData](
            success=True,
            data=HealthData(application="healthy", database="healthy"),
            error=None,
        )

    envelope = ResponseEnvelope[HealthData](
        success=False,
        data=HealthData(application="healthy", database="unavailable"),
        error="Database service unavailable",
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=envelope.model_dump(),
    )
