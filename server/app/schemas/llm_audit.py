"""Schemas and models for external LLM request audit records and security evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RedactionSummary(BaseModel):
    """Structured summary of sensitive information redacted from the payload."""

    total_redactions: int = Field(default=0, ge=0, description="Total number of sensitive items redacted")
    has_redactions: bool = Field(default=False, description="Whether any redaction was applied")
    categories: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of redactions grouped by category (e.g. api_keys, passwords, tokens, paths)",
    )
    detected_types: List[str] = Field(
        default_factory=list,
        description="List of detected secret categories that were sanitized",
    )


class SanitizedPromptPayload(BaseModel):
    """Sanitized prompt texts and message structure as delivered to the provider adapter."""

    system_prompt: str = Field(description="Sanitized system prompt text")
    user_prompt: str = Field(description="Sanitized user prompt context text")
    messages: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Structured message objects passed to provider completions API",
    )


class LLMRequestAuditItem(BaseModel):
    """Auditable record of a sanitized payload prepared and dispatched to an external LLM."""

    audit_id: str = Field(description="Unique audit record identifier")
    project_id: str = Field(description="Active project identifier enforcing tenant boundaries")
    event_id: Optional[str] = Field(default=None, description="Command execution run event ID")
    incident_id: Optional[str] = Field(default=None, description="Correlated failure incident ID")
    diagnosis_id: Optional[str] = Field(default=None, description="Correlated diagnosis ID if persisted")
    attempt: int = Field(default=1, ge=1, description="Diagnostic attempt index for retries/rechecks")
    provider: str = Field(description="LLM provider name (e.g. groq, mock, deterministic)")
    model: str = Field(description="Model identifier (e.g. llama-3.3-70b-versatile, mock-diagnostic-v1)")
    transmission_status: str = Field(
        description="Transmission lifecycle status: prepared, dispatched, completed, failed, blocked_by_policy"
    )
    sanitized_payload: SanitizedPromptPayload = Field(
        description="Sanitized prompt payload passed to provider adapter (never raw/unsanitized data)"
    )
    redaction_summary: RedactionSummary = Field(
        description="Counts and categories of redacted tokens and secrets"
    )
    payload_hash: str = Field(description="Deterministic SHA-256 hash of the sanitized payload")
    capture_boundary: str = Field(
        default="provider_adapter_input",
        description="Precise capture boundary: input to provider client adapter immediately before transmission",
    )
    created_at: datetime = Field(description="Timestamp when payload was prepared and verified safe")
    dispatched_at: Optional[datetime] = Field(default=None, description="Timestamp when request was dispatched")
    completed_at: Optional[datetime] = Field(default=None, description="Timestamp when provider responded or failed")
    duration_ms: Optional[float] = Field(default=None, description="Round-trip provider execution latency in ms")
    error_message: Optional[str] = Field(default=None, description="Sanitized provider error if failed")


class LLMSecuritySummary(BaseModel):
    """Aggregated security evidence statistics for the frontend security-monitor panel."""

    project_id: str = Field(description="Project identifier")
    total_requests: int = Field(ge=0, description="Total recorded LLM payload audits")
    status_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts by transmission status (prepared, dispatched, completed, failed, blocked_by_policy)",
    )
    total_redactions_applied: int = Field(
        ge=0,
        description="Total cumulative sensitive tokens redacted across all outbound requests",
    )
    redaction_categories: Dict[str, int] = Field(
        default_factory=dict,
        description="Cumulative redactions grouped by category (api_keys, passwords, tokens, paths)",
    )
    providers_used: List[str] = Field(default_factory=list, description="Unique list of LLM providers contacted")
    latest_transmission_at: Optional[datetime] = Field(default=None, description="Timestamp of most recent request")
