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
