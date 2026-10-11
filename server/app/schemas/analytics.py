"""Analytics and incident historical retrieval schemas."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from app.schemas.incident import IncidentResponse


class RecurringErrorItem(BaseModel):
    """Representative aggregation summary for a recurring error signature."""

    error_signature: str = Field(description="Normalized error signature grouping key")
    error_type: str = Field(description="Representative error type")
    error_message: str = Field(description="Representative error message")
    occurrence_count: int = Field(ge=1, description="Number of incidents with this signature")
    latest_occurrence: datetime = Field(description="Timestamp of most recent occurrence")


class RecurringErrorsResponse(BaseModel):
    """Response containing grouped recurring error analytics."""

    items: List[RecurringErrorItem] = Field(default_factory=list)
    total_groups: int = Field(ge=0, description="Total distinct recurring error groups")


class ProjectAnalyticsResponse(BaseModel):
    """High-level summary metrics calculated for a project."""

    project_id: str
    total_runs: int = Field(ge=0)
    successful_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    total_incidents: int = Field(ge=0)
    distinct_error_signatures: int = Field(ge=0)
    recent_incidents_24h: int = Field(ge=0)
    average_duration_ms: Optional[int] = Field(default=None, ge=0)


class CrossProjectIncidentSummary(BaseModel):
    """Sanitized incident summary safe for cross-project historical retrieval."""

    incident_id: str
    project_id: str
    error_type: str
    error_signature: str
    error_message: str = Field(description="Sanitized error message with paths and secrets redacted")
    created_at: datetime
    diagnosis_summary: Optional[str] = Field(default=None, description="High-level diagnosis if present")
    fix_status: Optional[str] = Field(default=None, description="Outcome of verified fix if present")


class GeneralKnowledgeMatchItem(BaseModel):
    """Curated general programming knowledge base match."""

    kb_id: str
    title: str
    explanation: str
    similarity_score: float = 1.0
    suggested_resolutions: List[str] = Field(default_factory=list)
    match_source: str = "general_knowledge"


class HistoricalMatchUnifiedItem(BaseModel):
    """Unified representation of historical match across project, cross-project, and knowledge base."""

    id: str
    source_id: str
    source_type: str  # 'project_memory', 'public_precedent', 'knowledge_base'
    is_cross_project: bool = False
    is_general_knowledge: bool = False
    source_project: str
    verified: bool = False
    similarity_score: float = 1.0
    match_reason: str
    sanitized_fix_summary: Optional[str] = None


class IncidentHistoryResponse(BaseModel):
    """Historical incident matches partitioned by same-project vs cross-project."""

    current_incident_id: str
    error_signature: str
    same_project_matches: List[IncidentResponse] = Field(default_factory=list)
    cross_project_matches: List[CrossProjectIncidentSummary] = Field(default_factory=list)
    general_knowledge_matches: List[GeneralKnowledgeMatchItem] = Field(default_factory=list)
    historical_matches: List[HistoricalMatchUnifiedItem] = Field(default_factory=list)
