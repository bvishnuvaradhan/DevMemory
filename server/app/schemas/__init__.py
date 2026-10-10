"""Pydantic schemas and response envelope models."""

from typing import Generic, Optional, TypeVar
from pydantic import BaseModel

from app.schemas.analytics import (
    CrossProjectIncidentSummary,
    IncidentHistoryResponse,
    ProjectAnalyticsResponse,
    RecurringErrorItem,
    RecurringErrorsResponse,
)
from app.schemas.diagnosis import (
    DiagnosisCreate,
    DiagnosisResponse,
    HypothesisItem,
    MatchedMemoryRef,
)
from app.schemas.fix import (
    FixOutcomeCreate,
    FixOutcomeResponse,
    FixOutcomeUpdate,
    FixStatus,
)
from app.schemas.incident import (
    IncidentCreate,
    IncidentResponse,
    IncidentEmbeddingResponse,
    EmbeddingBackfillResponse,
    EmbeddingProviderStatusResponse,
)
from app.schemas.pagination import PaginatedResponse
from app.schemas.performance import (
    BaselineCalculationRequest,
    CommandPerformanceSummary,
    PerformanceAnalyticsResponse,
    PerformanceBaselineResponse,
    PerformanceMeasurementCreate,
    PerformanceMeasurementResponse,
    RegressionStatus,
)
from app.schemas.project import ProjectCreate, ProjectResponse
from app.schemas.run import EnvironmentInfo, ErrorContext, RunCreate, RunResponse

T = TypeVar("T")


class ResponseEnvelope(BaseModel, Generic[T]):
    """Standardized API response envelope."""

    success: bool
    data: Optional[T] = None
    error: Optional[str] = None


class HealthData(BaseModel):
    """Health status details."""

    application: str
    database: str


__all__ = [
    "ResponseEnvelope",
    "HealthData",
    "PaginatedResponse",
    "ProjectCreate",
    "ProjectResponse",
    "RunCreate",
    "RunResponse",
    "EnvironmentInfo",
    "ErrorContext",
    "IncidentCreate",
    "IncidentResponse",
    "IncidentEmbeddingResponse",
    "EmbeddingBackfillResponse",
    "EmbeddingProviderStatusResponse",
    "RecurringErrorItem",
    "RecurringErrorsResponse",
    "ProjectAnalyticsResponse",
    "CrossProjectIncidentSummary",
    "IncidentHistoryResponse",
    "DiagnosisCreate",
    "DiagnosisResponse",
    "HypothesisItem",
    "MatchedMemoryRef",
    "FixOutcomeCreate",
    "FixOutcomeResponse",
    "FixOutcomeUpdate",
    "FixStatus",
    "RegressionStatus",
    "PerformanceMeasurementCreate",
    "PerformanceMeasurementResponse",
    "BaselineCalculationRequest",
    "PerformanceBaselineResponse",
    "CommandPerformanceSummary",
    "PerformanceAnalyticsResponse",
]
