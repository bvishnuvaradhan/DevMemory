"""Privacy and sanitization utilities for DevMemory AI & Memory Engine.

Provides functions to:
1. Redact API keys, bearer tokens, JWTs, cookies, private keys, certificates, and credentials.
2. Filter and exclude high-risk credential files (.env, private keys, service account configs).
3. Sanitize error messages, stack traces, and source snippets before LLM transmission.
4. Minimize outbound payload sizes (line budgeting, stack trace truncation).
5. Obfuscate absolute machine-specific user paths.
6. Defend against prompt-injection delimiters in untrusted input data.
7. Ensure cross-project data disclosure is strictly governed by server-side policy.
8. Validate outbound payload safety with policy checks before external transmission.

LIMITATIONS NOTICE:
Automated secret detection is pattern-based (heuristic/regex/structural) and defense-in-depth.
It cannot mathematically guarantee detection of every proprietary string or secret.
System operators should also maintain organizational credential governance.
"""

import copy
import re
from typing import Any, Dict, List, Optional

from ai_engine.schemas import DiagnosisRequest, SourceLocation, SourceSnippet

# --- Secret Detection Patterns ---

# Multi-line PEM Private Keys and Certificates
PEM_PRIVATE_KEY_REGEX = re.compile(
    r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9_-]+ )?PRIVATE KEY-----"
)
PEM_CERTIFICATE_REGEX = re.compile(
    r"-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----"
)

# Authentication Tokens & Standard Identity Envelopes
BEARER_TOKEN_REGEX = re.compile(r"(?i)\bBearer\s+([A-Za-z0-9_\-\.]{12,})\b")
JWT_REGEX = re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")
COOKIE_HEADER_REGEX = re.compile(r"(?i)\b(?:Set-Cookie|Cookie)\s*:\s*([^;\r\n\s]+)")
BASIC_AUTH_HEADER_REGEX = re.compile(r"(?i)\bAuthorization\s*:\s*Basic\s+([A-Za-z0-9+/=]{8,})\b")
AUTH_HEADER_GENERIC_REGEX = re.compile(r"(?i)\b(?:X-Api-Key|X-Auth-Token|Api-Key)\s*:\s*([A-Za-z0-9_\-\.]{8,})\b")

# Cloud and Vendor Token Patterns
AWS_KEY_REGEX = re.compile(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b")
AWS_SECRET_REGEX = re.compile(
    r"(?i)\b(?:aws_secret_access_key|aws_session_token)\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"
)
GITHUB_TOKEN_REGEX = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")
SLACK_TOKEN_REGEX = re.compile(r"\bxox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9_\-]*\b")
STRIPE_KEY_REGEX = re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9a-zA-Z]{24,}\b")
SENDGRID_KEY_REGEX = re.compile(r"\bSG\.[0-9a-zA-Z_-]{16,32}\.[0-9a-zA-Z_-]{32,64}\b")
OPENAI_KEY_REGEX = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}\b")
GENERIC_API_KEY_REGEX = re.compile(r"\b(?:gsk|sk|key)_[A-Za-z0-9_\-]{20,}\b")

# Connection Strings with Embedded Credentials (plain or percent-encoded)
URL_CREDENTIAL_REGEX = re.compile(
    r"(?i)(\b[a-z][a-z0-9+\-\.]*://[^:\s@/]+):([^@\s/]+)@"
)

# Key-Value and Variable Secret Assignments (both quoted and unquoted)
KEY_VALUE_QUOTED_SECRET_REGEX = re.compile(
    r'(?i)\b([A-Za-z0-9_]*(?:api[_-]?key|secret[_-]?key|client[_-]?secret|auth[_-]?token|access[_-]?token|'
    r'private[_-]?key|database[_-]?url|conn(?:ection)?[_-]?str(?:ing)?|password|passwd|pwd)[A-Za-z0-9_]*)\b\s*([:=]?)\s*(["\'])([^"\'\r\n\s,;]{4,})\3'
)
KEY_VALUE_UNQUOTED_SECRET_REGEX = re.compile(
    r'(?i)\b([A-Za-z0-9_]*(?:api[_-]?key|secret[_-]?key|client[_-]?secret|auth[_-]?token|access[_-]?token|'
    r'private[_-]?key|database[_-]?url|conn(?:ection)?[_-]?str(?:ing)?|password|passwd|pwd)[A-Za-z0-9_]*)\b\s*([:=])\s*([^"\'\r\n\s,;]{4,})'
)

# Local Machine Path Patterns for Obfuscation
WINDOWS_USER_PATH_REGEX = re.compile(
    r"(?i)[a-zA-Z]:[/\\](?:Users|Documents and Settings)[/\\][^/\\]+[/\\]"
)
UNIX_USER_PATH_REGEX = re.compile(r"/(?:Users|home)/[^/]+/")

# Sensitive File Patterns to Exclude Completely from AI Prompts
SENSITIVE_FILE_PATTERNS = [
    re.compile(r"(?i)(?:^|[/\\])\.env(?:\.[a-zA-Z0-9_-]+)?$"),
    re.compile(r"(?i)(?:^|[/\\])(?:id_rsa|id_ed25519|id_dsa|id_ecdsa)(?:\.pub)?$"),
    re.compile(r"(?i)\.(?:pem|key|pkcs12|pfx|p12)$"),
    re.compile(r"(?i)(?:credentials|secrets|service[-_]?account)\.(?:json|ya?ml|toml)$"),
    re.compile(r"(?i)[/\\](?:wp-config\.php|settings_local\.py)$"),
]

# Outbound Payload Budgets
MAX_STACK_TRACE_CHARS = 3000
MAX_SNIPPET_LINES = 40
MAX_SNIPPET_CHARS = 2000
MAX_OUTBOUND_SNIPPETS = 3
MAX_COMMAND_CHARS = 500
MAX_ERROR_MSG_CHARS = 2000


def is_sensitive_file(file_path: Optional[str]) -> bool:
    """Return True if the file path matches known high-risk credential or configuration patterns."""
    if not file_path:
        return False
    norm = file_path.replace("\\", "/")
    return any(pat.search(norm) for pat in SENSITIVE_FILE_PATTERNS)


def redact_secrets(text: Optional[str]) -> str:
    """Redact API keys, tokens, passwords, cookies, and credentials from a text string.
    
    Returns a sanitized copy. If text is None or empty, returns empty string.
    """
    if not text:
        return ""

    sanitized = text

    # 1. Multi-line PEM private keys and certificates
    sanitized = PEM_PRIVATE_KEY_REGEX.sub("[REDACTED_PRIVATE_KEY]", sanitized)
    sanitized = PEM_CERTIFICATE_REGEX.sub("[REDACTED_CERTIFICATE]", sanitized)

    # 2. URLs containing embedded passwords (plain and percent-encoded)
    sanitized = URL_CREDENTIAL_REGEX.sub(r"\1:[REDACTED_PASSWORD]@", sanitized)

    # 3. HTTP headers & session cookies
    sanitized = COOKIE_HEADER_REGEX.sub("Cookie: [REDACTED_COOKIE]", sanitized)
    sanitized = BASIC_AUTH_HEADER_REGEX.sub("Authorization: Basic [REDACTED_BASIC_AUTH]", sanitized)
    sanitized = AUTH_HEADER_GENERIC_REGEX.sub("X-Api-Key: [REDACTED_API_KEY]", sanitized)

    # 4. Bearer tokens & JWTs
    sanitized = BEARER_TOKEN_REGEX.sub("Bearer [REDACTED_TOKEN]", sanitized)
    sanitized = JWT_REGEX.sub("[REDACTED_JWT]", sanitized)

    # 5. Cloud provider and specific vendor tokens
    sanitized = AWS_KEY_REGEX.sub("[REDACTED_AWS_KEY]", sanitized)
    sanitized = AWS_SECRET_REGEX.sub(r"aws_secret_access_key=[REDACTED_AWS_SECRET]", sanitized)
    sanitized = GITHUB_TOKEN_REGEX.sub("[REDACTED_GITHUB_TOKEN]", sanitized)
    sanitized = SLACK_TOKEN_REGEX.sub("[REDACTED_SLACK_TOKEN]", sanitized)
    sanitized = STRIPE_KEY_REGEX.sub("[REDACTED_STRIPE_KEY]", sanitized)
    sanitized = SENDGRID_KEY_REGEX.sub("[REDACTED_SENDGRID_KEY]", sanitized)
    sanitized = OPENAI_KEY_REGEX.sub("[REDACTED_API_KEY]", sanitized)
    sanitized = GENERIC_API_KEY_REGEX.sub("[REDACTED_API_KEY]", sanitized)

    # 6. Key-value pairs with sensitive names
    sanitized = KEY_VALUE_QUOTED_SECRET_REGEX.sub(r"\1\2 \3[REDACTED_CREDENTIAL]\3", sanitized)
    sanitized = KEY_VALUE_UNQUOTED_SECRET_REGEX.sub(r"\1\2[REDACTED_CREDENTIAL]", sanitized)

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


def truncate_stack_trace(stack_trace: Optional[str], max_chars: int = MAX_STACK_TRACE_CHARS) -> Optional[str]:
    """Limit stack trace size to avoid sending excessive frames to external LLMs."""
    if not stack_trace or len(stack_trace) <= max_chars:
        return stack_trace
    half = max_chars // 2
    return (
        stack_trace[:half]
        + "\n\n[... TRUNCATED STACK FRAMES FOR PAYLOAD MINIMIZATION ...]\n\n"
        + stack_trace[-half:]
    )


def escape_prompt_delimiters(text: Optional[str]) -> str:
    """Escape section delimiters to defend against prompt injection breakout."""
    if not text:
        return ""
    # Transform lines starting with === into safe equivalent ---
    return re.sub(
        r"(?m)^(?:\s*)===\s*([A-Za-z0-9_\(\)]+(?:\s+[A-Za-z0-9_\(\)]+)*)\s*===",
        r"--- \1 ---",
        text,
    )


def sanitize_source_snippet(snippet: SourceSnippet) -> SourceSnippet:
    """Return a sanitized copy of a SourceSnippet without mutating the original.

    Enforces:
    - High-risk file exclusion (.env, keys).
    - Secret redaction.
    - Path normalization.
    - Snippet line and character budgeting.
    """
    clean_path = sanitize_file_path(snippet.file_path)

    # High-risk file exclusion
    if is_sensitive_file(snippet.file_path):
        return SourceSnippet(
            file_path=clean_path,
            start_line=snippet.start_line,
            end_line=snippet.end_line,
            content="[EXCLUDED_SENSITIVE_FILE_CONTENT: File matches sensitive credential/environment pattern and is excluded from AI payload]",
        )

    clean_content = redact_secrets(snippet.content)

    # Payload minimization: enforce line and character budget
    lines = clean_content.splitlines()
    if len(lines) > MAX_SNIPPET_LINES:
        clean_content = (
            "\n".join(lines[:MAX_SNIPPET_LINES])
            + "\n// [... REMAINING SNIPPET LINES TRUNCATED FOR PAYLOAD MINIMIZATION ...]"
        )
    if len(clean_content) > MAX_SNIPPET_CHARS:
        clean_content = clean_content[:MAX_SNIPPET_CHARS] + "\n// [... TRUNCATED ...]"

    return SourceSnippet(
        file_path=clean_path,
        start_line=snippet.start_line,
        end_line=snippet.end_line,
        content=clean_content,
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
    High-risk sensitive files are omitted.
    Excessive payloads are truncated to enforce outbound data minimization.
    """
    sanitized_cmd = sanitize_file_path(redact_secrets(request.command))
    if len(sanitized_cmd) > MAX_COMMAND_CHARS:
        sanitized_cmd = sanitized_cmd[:MAX_COMMAND_CHARS] + " [... TRUNCATED ...]"

    sanitized_msg = sanitize_file_path(redact_secrets(request.error_message))
    if len(sanitized_msg) > MAX_ERROR_MSG_CHARS:
        sanitized_msg = sanitized_msg[:MAX_ERROR_MSG_CHARS] + " [... TRUNCATED ...]"

    sanitized_stack = None
    if request.stack_trace:
        sanitized_stack = truncate_stack_trace(
            sanitize_file_path(redact_secrets(request.stack_trace)),
            max_chars=MAX_STACK_TRACE_CHARS,
        )

    # Sanitize locations (budgeted to top 10 frames)
    sanitized_locs = [sanitize_source_location(loc) for loc in request.locations[:10]]

    # Sanitize snippets and enforce maximum count budget
    sanitized_snippets = [
        sanitize_source_snippet(snip) for snip in request.source_snippets[:MAX_OUTBOUND_SNIPPETS]
    ]

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


def validate_outbound_payload_safety(text: str) -> Dict[str, Any]:
    """Inspect outbound prompt payload to ensure no high-risk raw credentials or private keys remain.

    Returns:
        Dict with "is_safe" (bool) and "violations" (List[str]).
    """
    violations = []

    if PEM_PRIVATE_KEY_REGEX.search(text):
        violations.append("Contains unredacted PEM private key block")

    if AWS_KEY_REGEX.search(text):
        violations.append("Contains unredacted AWS access key identifier")

    if GITHUB_TOKEN_REGEX.search(text):
        violations.append("Contains unredacted GitHub personal access token")

    if SLACK_TOKEN_REGEX.search(text):
        violations.append("Contains unredacted Slack token")

    if STRIPE_KEY_REGEX.search(text):
        violations.append("Contains unredacted Stripe secret key")

    if OPENAI_KEY_REGEX.search(text):
        violations.append("Contains unredacted OpenAI secret key")

    # Check for raw passwords in URL connection strings (ignore already redacted ones)
    url_cred_matches = URL_CREDENTIAL_REGEX.findall(text)
    for match in url_cred_matches:
        if match[1] != "[REDACTED_PASSWORD]":
            violations.append("Contains unredacted password in connection URL")
            break

    # Check for raw JWTs (ignore already redacted)
    for jwt_match in JWT_REGEX.findall(text):
        if "[REDACTED_JWT]" not in jwt_match:
            violations.append("Contains unredacted JSON Web Token")
            break

    return {
        "is_safe": len(violations) == 0,
        "violations": violations,
    }


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
