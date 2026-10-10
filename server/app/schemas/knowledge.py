"""Schemas for curated programming knowledge base."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class KnowledgeBaseItemModel(BaseModel):
    """Schema representing an individual programming knowledge base entry."""

    kb_id: str = Field(..., description="Stable unique identifier for knowledge entry")
    title: str = Field(..., description="Short descriptive title of the problem")
    error_pattern: str = Field(..., description="Canonical error signature or message pattern")
    language: str = Field(default="general", description="Language, framework, or tool (python, javascript, http, mongodb, etc.)")
    category: str = Field(default="general", description="Category of error (runtime, network, configuration, database, etc.)")
    explanation: str = Field(..., description="Concise explanation of the error mechanism")
    possible_causes: List[str] = Field(default_factory=list, description="Common causes leading to this error")
    diagnostic_checks: List[str] = Field(default_factory=list, description="Safe diagnostic steps to isolate the issue")
    suggested_resolutions: List[str] = Field(default_factory=list, description="Recommended remediation steps")
    tags: List[str] = Field(default_factory=list, description="Searchable keyword tags")
    source_type: str = Field(default="knowledge_base", description="Provenance marker")
    embedding_model: Optional[str] = Field(default=None, description="Embedding model used for dense vector")
    embedding_dimension: Optional[int] = Field(default=None, description="Dimensionality of embedding vector")
    embedding_status: Optional[str] = Field(default=None, description="Embedding status (live_success, deterministic_fallback, etc.)")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class KnowledgeBaseCreate(BaseModel):
    """Payload to create or update a knowledge base entry."""

    kb_id: str
    title: str
    error_pattern: str
    language: str = "general"
    category: str = "general"
    explanation: str
    possible_causes: List[str] = Field(default_factory=list)
    diagnostic_checks: List[str] = Field(default_factory=list)
    suggested_resolutions: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class KnowledgeBaseSeedResponse(BaseModel):
    """Result report of seeding the curated knowledge base."""

    total_curated: int
    inserted: int
    updated: int
    unchanged: int
    embedding_provider: str
    embedding_status: str
    embedding_dimension: int
    message: str


class KnowledgeBaseMatch(BaseModel):
    """Search match from knowledge base."""

    kb_id: str
    title: str
    error_pattern: str
    language: str
    category: str
    explanation: str
    suggested_resolutions: List[str]
    similarity_score: float
    source: str = "knowledge_base"
