"""Deterministic error signature generation, sanitization, and normalization utilities."""

import hashlib
import re


def sanitize_error_message(message: str) -> str:
    """Sanitize error messages for privacy-safe cross-project sharing.

    Strips:
    - User home paths (e.g. C:\\Users\\username\\... or /home/username/...)
    - Internal filesystem paths
    - Authorization headers, tokens, and secret patterns
    - IP addresses and internal hostnames
    """
    if not message:
        return ""

    sanitized = message

    # 1. Redact API tokens, secrets, and auth headers
    sanitized = re.sub(
        r"(?i)\b(bearer|token|secret|password|api[_-]?key|auth)[\s=:]+([a-zA-Z0-9_\-\.]{8,})",
        r"\1 <REDACTED>",
        sanitized,
    )
    sanitized = re.sub(r"\b(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{30,}\b", "<TOKEN>", sanitized)
    sanitized = re.sub(r"\bsk-[a-zA-Z0-9]{20,}\b", "<TOKEN>", sanitized)

    # 2. Redact user directories in paths (Windows & POSIX)
    sanitized = re.sub(r"(?i)[a-zA-Z]:\\Users\\[^\s\\:\"']+", r"<USER_HOME>", sanitized)
    sanitized = re.sub(r"/home/[^\s/:\"']+", r"<USER_HOME>", sanitized)
    sanitized = re.sub(r"/Users/[^\s/:\"']+", r"<USER_HOME>", sanitized)

    # 3. Redact full directory paths down to file basenames where appropriate
    sanitized = re.sub(r"[a-zA-Z]:\\[^\s:\"']+\\([^\s\\:\"']+)", r"<PATH>\\\1", sanitized)
    sanitized = re.sub(r"/(?:[a-zA-Z0-9_\.\-]+/)+([a-zA-Z0-9_\.\-]+)", r"<PATH>/\1", sanitized)

    # 4. Redact IPv4 addresses
    sanitized = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", "<HOST:PORT>", sanitized)

    return sanitized.strip()


def compute_error_signature(error_type: str, error_message: str) -> str:
    """Compute a deterministic, sanitized error signature.

    Normalizes:
    - Error types and case
    - Hexadecimal memory addresses (e.g. 0x7fff5fbff8a0)
    - Filesystem paths (Windows and POSIX)
    - Contextual location suffixes (e.g. 'in <path>', 'at <path>')
    - Tokens and credentials
    - UUIDs and long hexadecimal digests
    - Datetime strings
    - Line/column numbers embedded in error messages
    - Dynamic numbers (run numbers, thread IDs, counters)
    - Consecutive whitespace

    Returns:
        A deterministic signature string like: sig_<normalized_type>_<hash12>
    """
    clean_type = (error_type or "UnknownError").strip()
    msg = (error_message or "").strip().lower()

    # 1. Normalize hexadecimal memory addresses: 0x[0-9a-fA-F]+
    msg = re.sub(r"0x[0-9a-fA-F]+", "<hex>", msg)

    # 2. Normalize full file paths (Windows e.g. C:\... and POSIX /...)
    msg = re.sub(r"[a-zA-Z]:\\[^\s:\"']+", "<path>", msg)
    msg = re.sub(r"/(?:[a-zA-Z0-9_\.\-]+/)+[a-zA-Z0-9_\.\-]+", "<path>", msg)

    # 3. Normalize IP addresses / hosts
    msg = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", "<host>", msg)

    # 4. Normalize tokens / secrets
    msg = re.sub(
        r"(?i)\b(bearer|token|secret|password|api[_-]?key)[\s=:]+([a-zA-Z0-9_\-\.]{8,})",
        r"\1 <token>",
        msg,
    )
    msg = re.sub(r"\b(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{30,}\b", "<token>", msg)
    msg = re.sub(r"\bsk-[a-zA-Z0-9]{20,}\b", "<token>", msg)

    # 5. Normalize UUIDs and long hexadecimal digests (24 to 64 chars)
    msg = re.sub(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        "<uuid>",
        msg,
    )
    msg = re.sub(r"\b[0-9a-fA-F]{24,64}\b", "<hash>", msg)

    # 6. Normalize timestamps / ISO dates
    msg = re.sub(
        r"\d{4}-\d{2}-\d{2}[tT\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?",
        "<datetime>",
        msg,
    )

    # 7. Normalize line and column references
    msg = re.sub(r"\b(?:line|col|column)\s*\d+\b", "<loc>", msg)
    msg = re.sub(r":\d+:\d+", ":<loc>", msg)

    # 8. Strip contextual file/location suffixes so core error messages group across systems
    msg = re.sub(r"\s+\b(?:at|in|from|file)\s+<path>(?::\S+)?", "", msg)
    msg = re.sub(r"\s+\b(?:at|in|on)\s+<loc>", "", msg)
    msg = re.sub(r"\s+\b(?:bearer|token|secret|password|api[_-]?key)\s+<token>", "", msg)

    # 9. Normalize standalone numeric counters / iterations / IDs
    msg = re.sub(r"\b\d+\b", "<num>", msg)

    # 10. Normalize quotes
    msg = msg.replace('"', "'")

    # 11. Collapse excess whitespace
    msg = re.sub(r"\s+", " ", msg).strip()

    # Hash the normalized type and message
    digest = hashlib.sha256(f"{clean_type}::{msg}".encode("utf-8")).hexdigest()[:12]
    type_slug = re.sub(r"[^a-zA-Z0-9_]", "_", clean_type)[:32]
    return f"sig_{type_slug}_{digest}"
