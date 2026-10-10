"""Pydantic schemas for fix proposals, application, and verification tracking."""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

FixStatus = Literal["proposed", "applied", "verifying", "verified", "failed", "reverted"]


class FixOutcomeCreate(BaseModel):
    """Payload to register a proposed fix for an incident."""

    fix_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Optional client-specified stable fix ID for idempotency",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Explanation of the proposed solution or code fix",
    )


class FixOutcomeUpdate(BaseModel):
    """Payload to update fix status and attach verification evidence."""

    status: Optional[FixStatus] = Field(
        default=None,
        description="Target lifecycle state ('applied', 'verifying', 'verified', 'failed', 'reverted')",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Updated explanation of the fix",
    )
    verification_method: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Verification approach ('command', 'test_runner', 'user_confirmation')",
    )
    verification_command: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Command that was executed to test the fix",
    )
    verification_exit_code: Optional[int] = Field(
        default=None,
        description="Actual exit code returned by the verification command (0 indicates success)",
    )
    verification_details: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Sanitized summary of verification outcome",
    )
    verification_source: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Source of verification ('automated_command', 'test_runner', 'user_confirmation')",
    )


class FixOutcomeResponse(BaseModel):
    """Complete fix record with verification status."""

    fix_id: str
    incident_id: str
    project_id: str
    description: str
    status: str
    verification_method: Optional[str] = None
    verification_command: Optional[str] = None
    verification_exit_code: Optional[int] = None
    verification_details: Optional[str] = None
    verification_source: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
