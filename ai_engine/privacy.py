"""Privacy and sanitization utilities for DevMemory AI & Memory Engine.

Provides functions to:
1. Redact common API keys, bearer tokens, passwords, and secrets.
2. Sanitize error messages, stack traces, and source snippets before LLM transmission.
3. Obfuscate absolute machine-specific user paths.
4. Ensure cross-project data disclosure is strictly governed by server-side policy.
5. Guarantee original diagnostic records remain intact and separate from sanitized copies.

LIMITATIONS NOTICE:
Automated secret detection is pattern-based (heuristic/regex) and best-effort.
It cannot mathematically guarantee detection of every proprietary string or secret.
System operators should also maintain organizational credential governance.
"""

import copy
import re
from typing import Any, Dict, List, Optional

from ai_engine.schemas import DiagnosisRequest, SourceLocation, SourceSnippet


# Common credential regex patterns
BEARER_TOKEN_REGEX = re.compile(r"(?i)\bBearer\s+([A-Za-z0-9_\-\.]{12,})\b")
JWT_REGEX = re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")
AWS_KEY_REGEX = re.compile(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b")
GITHUB_TOKEN_REGEX = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")
GENERIC_API_KEY_REGEX = re.compile(r"\b(?:gsk|sk|key)_[A-Za-z0-9_\-]{20,}\b")

# Key-value secret assignments: e.g. api_key="secret", password: '123'
KEY_VALUE_SECRET_REGEX = re.compile(
    r'(?i)\b(api[_-]?key|secret[_-]?key|client[_-]?secret|auth[_-]?token|access[_-]?token|'
    r'private[_-]?key|password|passwd|pwd)\b\s*([:=])\s*(["\']?)([^"\'\s,;]{6,})\3'
)

# Password in connection URLs: http(s)://user:password@host
URL_CREDENTIAL_REGEX = re.compile(r"(?i)(\b[a-z]{3,10}://[^:\s@]+):([^@\s/]+)@")

# Path obfuscation patterns for local machine directories
WINDOWS_USER_PATH_REGEX = re.compile(
    r"(?i)[a-zA-Z]:[/\\](?:Users|Documents and Settings)[/\\][^/\\]+[/\\]"
)
UNIX_USER_PATH_REGEX = re.compile(r"/(?:Users|home)/[^/]+/")




def redact_secrets(text: Optional[str]) -> str:
    """Redact API keys, tokens, passwords, and credentials from a text string.
    
    Returns a sanitized copy. If text is None or empty, returns empty string.
    """
    if not text:
        return ""

    sanitized = text

    # Redact URLs containing embedded passwords
    sanitized = URL_CREDENTIAL_REGEX.sub(r"\1:[REDACTED_PASSWORD]@", sanitized)

    # Redact Bearer tokens
    sanitized = BEARER_TOKEN_REGEX.sub("Bearer [REDACTED_TOKEN]", sanitized)

    # Redact JWT tokens
    sanitized = JWT_REGEX.sub("[REDACTED_JWT]", sanitized)

    # Redact specific vendor tokens
    sanitized = AWS_KEY_REGEX.sub("[REDACTED_AWS_KEY]", sanitized)
    sanitized = GITHUB_TOKEN_REGEX.sub("[REDACTED_GITHUB_TOKEN]", sanitized)
    sanitized = GENERIC_API_KEY_REGEX.sub("[REDACTED_API_KEY]", sanitized)

    # Redact key-value pairs with sensitive names
    sanitized = KEY_VALUE_SECRET_REGEX.sub(r"\1\2\3[REDACTED_CREDENTIAL]\3", sanitized)

    return sanitized


def sanitize_file_path(file_path: Optional[str]) -> str:
    """Normalize file paths to avoid exposing machine-specific usernames or drive roots.
    
    Transforms:
        C:\\Users\\alice\\projects\\app\\main.py -> ~/projects/app/main.py
        /home/bob/projects/app/main.py -> ~/projects/app/main.py
    """
    if not file_path:
        return ""

    sanitized = file_path.replace("\\", "/")
    sanitized = WINDOWS_USER_PATH_REGEX.sub("~/", sanitized)
    sanitized = UNIX_USER_PATH_REGEX.sub("~/", sanitized)
    return sanitized


def sanitize_source_snippet(snippet: SourceSnippet) -> SourceSnippet:
    """Return a sanitized copy of a SourceSnippet without mutating the original."""
    return SourceSnippet(
        file_path=sanitize_file_path(snippet.file_path),
        start_line=snippet.start_line,
        end_line=snippet.end_line,
        content=redact_secrets(snippet.content),
    )


def sanitize_source_location(loc: SourceLocation) -> SourceLocation:
    """Return a sanitized copy of a SourceLocation without mutating the original."""
    return SourceLocation(
        file_path=sanitize_file_path(loc.file_path),
        line=loc.line,
        column=loc.column,
        function_name=loc.function_name,
    )


def sanitize_diagnosis_request(request: DiagnosisRequest) -> DiagnosisRequest:
    """Create a sanitized copy of DiagnosisRequest suitable for external LLM transmission.
    
    The original request instance is NOT mutated.
    Sensitive tokens in error_message, stack_trace, command, and snippets are redacted.
    Absolute machine paths are normalized.
    """
    sanitized_cmd = sanitize_file_path(redact_secrets(request.command))
    sanitized_msg = sanitize_file_path(redact_secrets(request.error_message))
    sanitized_stack = sanitize_file_path(redact_secrets(request.stack_trace)) if request.stack_trace else None


    # Sanitize locations and snippets
    sanitized_locs = [sanitize_source_location(loc) for loc in request.locations]
    sanitized_snippets = [sanitize_source_snippet(snip) for snip in request.source_snippets]

    return DiagnosisRequest(
        event_id=request.event_id,
        project_id=request.project_id,
        command=sanitized_cmd,
        exit_code=request.exit_code,
        error_message=sanitized_msg,
        stack_trace=sanitized_stack,
        locations=sanitized_locs,
        source_snippets=sanitized_snippets,
        allow_cross_project=request.allow_cross_project,
    )


def is_cross_project_sharing_permitted(
    requester_project_id: str,
    candidate_project_id: str,
    candidate_is_public: bool,
    requester_prefers_cross_project: bool = True,
) -> bool:
    """Enforce server-side authorization policy for cross-project incident sharing.
    
    Rules:
    - Same-project retrieval is always permitted.
    - Cross-project sharing is permitted ONLY if:
        1. The candidate project explicitly has public sharing enabled (candidate_is_public=True).
        2. The requesting user has not opted out (requester_prefers_cross_project=True).
    - Client-side preference cannot grant access to candidate projects where candidate_is_public=False.
    """
    # Same project is always within boundary
    if requester_project_id == candidate_project_id:
        return True

    # Candidate project must be authorized for sharing by its owner/server
    if not candidate_is_public:
        return False

    # Requester must also have cross-project preference active
    return requester_prefers_cross_project
