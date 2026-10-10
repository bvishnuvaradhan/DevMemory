from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

CLIENT_SCHEMA_VERSION = "1.0.0"

# Common patterns for API keys, tokens, bearer headers, and passwords
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|apikey|secret|token|password|auth[_-]?token|bearer\s+[a-zA-Z0-9_\-\.]+)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"),
    re.compile(r"(?i)(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})"),
    re.compile(r"(?i)(sk-[a-zA-Z0-9]{32,}|gsk_[a-zA-Z0-9]{32,})"),
    re.compile(r"(?i)(mongodb(?:\+srv)?:\/\/[^\/\s]+:[^\/\s@]+@)"),
]


def redact_secrets(text: str) -> str:
    """
    Redact potential secrets (API keys, tokens, passwords, database connection URIs)
    from text evidence before sending outside the local environment.
    """
    if not text:
        return ""

    sanitized = text
    for pattern in SECRET_PATTERNS:
        def _replace_match(match: re.Match[str]) -> str:
            full_val = match.group(0)
            if len(match.groups()) >= 2:
                # e.g. key: "secret_value"
                prefix = match.group(1)
                secret = match.group(2)
                return f"{prefix}: [REDACTED]"
            elif "mongodb" in full_val.lower():
                return "mongodb://[REDACTED_AUTH]@"
            else:
                return "[REDACTED_SECRET]"

        sanitized = pattern.sub(_replace_match, sanitized)
    return sanitized


@dataclass
class IncidentSourceSnippet:
    """Validated source snippet within an incident frame."""
    file_path: str
    target_line: int
    target_col: Optional[int]
    start_line: int
    end_line: int
    lines: List[str]
    is_safe: bool = True
    error: Optional[str] = None


@dataclass
class IncidentStackFrame:
    """Stack frame included in the incident payload."""
    raw_frame: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    function_name: Optional[str] = None
    code_line: Optional[str] = None
    is_project_file: bool = False
    snippet: Optional[IncidentSourceSnippet] = None


@dataclass
class IncidentErrorInfo:
    """Detailed error diagnostics for the incident."""
    language: str
    error_type: str
    message: str
    frames: List[IncidentStackFrame] = field(default_factory=list)
    primary_frame: Optional[IncidentStackFrame] = None
    raw_traceback: str = ""
    confidence: float = 0.0
    has_diagnostic: bool = False


@dataclass
class IncidentPayload:
    """
    The standardized incident payload sent to the backend ingestion endpoint.
    Covers event identity, project context, command metrics, sanitized outputs, and diagnostic data.
    """
    event_id: str
    project_id: str
    project_name: str
    command: List[str]
    cwd: str
    started_at: str
    ended_at: str
    duration_ms: float
    exit_code: int
    interrupted: bool
    stdout: str
    stderr: str
    error_info: Optional[IncidentErrorInfo] = None
    client_version: str = CLIENT_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Serialize payload dataclass to a JSON-compatible dictionary."""
        return asdict(self)


@dataclass
class SimilarIncidentMatch:
    """Historical or cross-project incident match returned by backend memory search."""
    incident_id: str
    project_name: str
    similarity_score: float
    summary: str
    verified_fix: Optional[str] = None
    is_cross_project: bool = False


@dataclass
class BackendDiagnosisResponse:
    """
    Structured diagnosis returned by the backend (Member 2/Member 3).
    """
    status: str  # "success", "error", "no_diagnosis"
    event_id: str
    probable_cause: Optional[str] = None
    hypotheses: List[str] = field(default_factory=list)
    suggested_steps: List[str] = field(default_factory=list)
    similar_incidents: List[SimilarIncidentMatch] = field(default_factory=list)
    knowledge_base_match: Optional[str] = None
    is_verified_fix: bool = False
    raw_response: Optional[Dict[str, Any]] = None
