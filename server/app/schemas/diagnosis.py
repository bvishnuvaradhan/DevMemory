"""Pydantic schemas for AI diagnosis records."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class HypothesisItem(BaseModel):
    """Hypothesis distinguishing observed facts from speculation."""

    cause: str = Field(..., min_length=1, max_length=1000, description="Potential root cause")
    is_observed: bool = Field(
        default=False,
        description="True if supported by direct log/code evidence, False if hypothesis",
    )
    details: Optional[str] = Field(default=None, max_length=2000, description="Explanatory context")


class MatchedMemoryRef(BaseModel):
    """Reference to historical incident or general knowledge item."""

    source_id: str = Field(..., min_length=1, max_length=128, description="Incident or KB reference ID")
    source_type: str = Field(..., description="'incident' or 'knowledge_base'")
    relevance_reason: Optional[str] = Field(default=None, max_length=1000, description="Why this memory applies")


class DiagnosisCreate(BaseModel):
    """Payload for storing a structured AI diagnosis."""

    diagnosis_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Optional client-specified stable diagnosis ID for idempotency",
    )
    summary: str = Field(..., min_length=1, max_length=2000, description="Executive explanation of the error")
    hypotheses: List[HypothesisItem] = Field(
        default_factory=list,
        description="Structured hypotheses distinguishing evidence from speculation",
    )
    suggested_fix: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Recommended remediation steps or proposed code change",
    )
    matched_memory: List[MatchedMemoryRef] = Field(
        default_factory=list,
        description="References to historical incidents or knowledge-base entries",
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Direct observed facts from command output and stack traces",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional bounded confidence score (0.0 to 1.0)",
    )
    source: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Originating AI model or diagnostic system (e.g. 'groq/llama-3.3-70b')",
    )


class DiagnosisResponse(BaseModel):
    """Full diagnosis details response."""

    diagnosis_id: str
    incident_id: str
    project_id: str
    summary: str
    hypotheses: List[HypothesisItem] = Field(default_factory=list)
    suggested_fix: Optional[str] = None
    matched_memory: List[MatchedMemoryRef] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    source: Optional[str] = None
    created_at: datetime
    idempotent: bool = False
