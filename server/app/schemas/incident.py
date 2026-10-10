"""Incident schemas and models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class IncidentCreate(BaseModel):
    """Schema for direct incident registration."""

    project_id: str = Field(..., min_length=1, max_length=64)
    event_id: Optional[str] = Field(default=None, max_length=128)
    error_type: str = Field(..., min_length=1, max_length=120)
    error_message: str = Field(..., min_length=1, max_length=4000)
    file_path: Optional[str] = Field(default=None, max_length=500)
    line: Optional[int] = Field(default=None, ge=1)
    column: Optional[int] = Field(default=None, ge=1)
    source_snippet: Optional[str] = Field(default=None, max_length=10000)


class IncidentResponse(BaseModel):
    """Schema for incident data responses."""

    incident_id: str
    event_id: Optional[str] = None
    project_id: str
    error_type: str
    error_message: str
    error_signature: str
    file_path: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    source_snippet: Optional[str] = None
    diagnosis_status: str = "pending"
    created_at: datetime
    # Embedding metadata (optional for backward compatibility)
    embedding: Optional[list[float]] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    embedding_status: Optional[str] = None
    embedding_is_fallback: Optional[bool] = None
    embedded_at: Optional[datetime] = None


class IncidentEmbeddingResponse(BaseModel):
    """Schema for incident embedding metadata and vector response."""

    incident_id: str
    project_id: str
    embedding: list[float]
    embedding_model: str
    embedding_dimension: int
    embedding_status: str
    embedding_is_fallback: bool
    canonical_text: Optional[str] = None
    embedded_at: Optional[datetime] = None


class EmbeddingBackfillResponse(BaseModel):
    """Schema for embedding backfill execution summary."""

    total_scanned: int
    updated: int
    skipped: int
    failed: int
    embedding_model: str
    embedding_dimension: int


class EmbeddingProviderStatusResponse(BaseModel):
    """Schema for embedding provider readiness check."""

    provider_type: str
    configured_model: str
    target_dimension: int
    credentials_configured: bool
    status: str
    is_live: bool
    reason: Optional[str] = None
    masked_credential: Optional[str] = None


class VectorSearchStatusResponse(BaseModel):
    """Schema for Atlas Vector Search readiness and index status."""

    index_name: str
    status: str
    queryable: bool
    vector_field: str
    target_dimension: int
    provider_type: str
    fallback_available: bool = True
    message: Optional[str] = None


class VectorSearchMatchItem(BaseModel):
    """Schema for individual semantic vector match."""

    incident_id: str
    project_id: Optional[str] = None
    error_message: str
    similarity_score: float
    command: Optional[str] = None
    stack_trace: Optional[str] = None
    resolution_summary: Optional[str] = None
    verification_status: str = "unverified"
    is_public: bool = False
    source: str = "vector_search"
