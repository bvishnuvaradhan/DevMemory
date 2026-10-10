"""Command-run ingestion and retrieval schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class EnvironmentInfo(BaseModel):
    """Execution environment details."""

    os: Optional[str] = Field(default=None, max_length=100)
    runtime_version: Optional[str] = Field(default=None, max_length=100)
    git_branch: Optional[str] = Field(default=None, max_length=100)
    git_commit: Optional[str] = Field(default=None, max_length=64)


class ErrorContext(BaseModel):
    """Source-aware error context parsed from output or stack trace."""

    error_type: Optional[str] = Field(default=None, max_length=120)
    message: Optional[str] = Field(default=None, max_length=4000)
    file_path: Optional[str] = Field(default=None, max_length=500)
    line: Optional[int] = Field(default=None, ge=1)
    column: Optional[int] = Field(default=None, ge=1)
    snippet: Optional[str] = Field(default=None, max_length=10000)


class RunCreate(BaseModel):
    """Payload for ingesting a command execution event."""

    event_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Client-generated stable event ID (UUID or prefixed slug)",
    )
    project_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Associated project identifier",
    )
    command: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Command line that was executed",
    )
    exit_code: int = Field(
        ...,
        description="Process exit code (0 indicates success)",
    )
    duration_ms: int = Field(
        ...,
        ge=0,
        description="Execution duration in milliseconds",
    )
    stdout: Optional[str] = Field(
        default="",
        max_length=100000,
        description="Captured standard output",
    )
    stderr: Optional[str] = Field(
        default="",
        max_length=100000,
        description="Captured standard error",
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when command began",
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when command completed",
    )
    environment: Optional[EnvironmentInfo] = Field(
        default=None,
        description="System and runtime environment metadata",
    )
    error_context: Optional[ErrorContext] = Field(
        default=None,
        description="Extracted stack trace and source location info",
    )


class RunResponse(BaseModel):
    """Full command run details response."""

    event_id: str
    project_id: str
    command: str
    exit_code: int
    status: str
    duration_ms: int
    stdout: str = ""
    stderr: str = ""
    started_at: datetime
    finished_at: datetime
    created_at: datetime
    environment: Optional[EnvironmentInfo] = None
    error_context: Optional[ErrorContext] = None
    idempotent: bool = False
    incident_id: Optional[str] = None
