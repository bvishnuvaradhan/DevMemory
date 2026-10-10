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
class BackendErrorContext:
    """Error context matching Member 2's server/app/schemas/run.py ErrorContext schema."""
    error_type: Optional[str] = None
    message: Optional[str] = None
    file_path: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BackendEnvironmentInfo:
    """Environment details matching Member 2's EnvironmentInfo schema."""
    os: Optional[str] = None
    runtime_version: Optional[str] = None
    git_branch: Optional[str] = None
    git_commit: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
    """Stack frame included in local incident diagnostic reporting."""
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
    """Detailed error diagnostics for local CLI reporting."""
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
    Standardized payload sent to Member 2's POST /api/v1/runs endpoint.
    Guarantees strict compliance with server/app/schemas/run.py RunCreate.
    """
    event_id: str
    project_id: str
    command: str  # Serialized command string as required by RunCreate
    exit_code: int
    duration_ms: int  # Integer milliseconds
    stdout: str = ""
    stderr: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    ended_at: Optional[str] = None
    environment: Optional[BackendEnvironmentInfo] = None
    error_context: Optional[BackendErrorContext] = None
    # Additional CLI-internal metadata
    project_name: str = ""
    cwd: str = ""
    interrupted: bool = False
    client_version: str = CLIENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.ended_at and not self.finished_at:
            self.finished_at = self.ended_at
        elif self.finished_at and not self.ended_at:
            self.ended_at = self.finished_at

    def to_dict(self) -> Dict[str, Any]:
        """Serialize into dictionary strictly conforming to server/app/schemas/run.py RunCreate."""
        res: Dict[str, Any] = {
            "event_id": self.event_id,
            "project_id": self.project_id,
            "command": self.command,
            "exit_code": self.exit_code,
            "duration_ms": int(self.duration_ms),
            "stdout": self.stdout or "",
            "stderr": self.stderr or "",
        }
        if self.started_at:
            res["started_at"] = self.started_at
        if self.finished_at or self.ended_at:
            res["finished_at"] = self.finished_at or self.ended_at
        if self.environment:
            res["environment"] = self.environment.to_dict()
        if self.error_context:
            res["error_context"] = self.error_context.to_dict()
        return res


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
    """Structured diagnosis returned or fetched from the backend."""
    status: str  # "success", "error", "no_diagnosis"
    event_id: str
    incident_id: Optional[str] = None
    probable_cause: Optional[str] = None
    hypotheses: List[str] = field(default_factory=list)
    suggested_steps: List[str] = field(default_factory=list)
    similar_incidents: List[SimilarIncidentMatch] = field(default_factory=list)
    knowledge_base_match: Optional[str] = None
    is_verified_fix: bool = False
    raw_response: Optional[Dict[str, Any]] = None
