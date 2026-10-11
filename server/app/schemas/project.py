"""Project registration and retrieval Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator


class ProjectCreate(BaseModel):
    """Schema for registering or creating a new project."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Human-readable project name",
    )
    project_id: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=64,
        description="Optional unique stable identifier (e.g. 'proj_shopapp')",
    )
    language: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Primary programming language (e.g. 'python', 'javascript')",
    )
    settings: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional project-specific configurations",
    )

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                return None
            import re
            if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
                raise ValueError("project_id may only contain alphanumeric characters, hyphens, and underscores.")
        return v


class ProjectResponse(BaseModel):
    """Schema for project responses."""

    project_id: str
    name: str
    description: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None
    repository: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    total_runs: Optional[int] = Field(default=None, ge=0)
    failure_count: Optional[int] = Field(default=None, ge=0)
    verified_fix_count: Optional[int] = Field(default=None, ge=0)
    median_duration_ms: Optional[int] = Field(default=None, ge=0)
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
