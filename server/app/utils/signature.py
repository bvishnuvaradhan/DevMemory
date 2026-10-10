"""Deterministic error signature generation and normalization utilities."""

import hashlib
import re


def compute_error_signature(error_type: str, error_message: str) -> str:
    """Compute a deterministic, sanitized error signature.

    Normalizes:
    - Error types and case
    - Hexadecimal memory addresses (e.g. 0x7fff5fbff8a0)
    - Filesystem paths (Windows and POSIX)
    - UUIDs and long alphanumeric hashes
    - Datetime strings
    - Line/column numbers embedded in error messages
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

    # 3. Normalize UUIDs and long hexadecimal digests (24 to 64 chars)
    msg = re.sub(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        "<uuid>",
        msg,
    )
    msg = re.sub(r"\b[0-9a-fA-F]{24,64}\b", "<hash>", msg)

    # 4. Normalize timestamps / ISO dates
    msg = re.sub(r"\d{4}-\d{2}-\d{2}[tT\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?", "<datetime>", msg)

    # 5. Normalize line and column references
    msg = re.sub(r"\b(?:line|col|column)\s*\d+\b", "<loc>", msg)
    msg = re.sub(r":\d+:\d+", ":<loc>", msg)

    # 6. Normalize integer IDs or numeric tokens surrounded by non-digits
    msg = re.sub(r"\b\d{4,}\b", "<num>", msg)

    # 7. Collapse excess whitespace
    msg = re.sub(r"\s+", " ", msg).strip()

    # Hash the normalized type and message
    digest = hashlib.sha256(f"{clean_type}::{msg}".encode("utf-8")).hexdigest()[:12]
    type_slug = re.sub(r"[^a-zA-Z0-9_]", "_", clean_type)[:32]
    return f"sig_{type_slug}_{digest}"
