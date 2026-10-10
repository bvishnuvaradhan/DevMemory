"""Deterministic command normalization, sanitization, and signature generation utilities."""

import hashlib
import re
from typing import Tuple


def sanitize_command(command: str) -> str:
    """Sanitize command strings by removing sensitive tokens, passwords, and private paths.

    Strips:
    - User home directories (e.g. C:\\Users\\username\\... or /home/username/...)
    - Authorization headers, tokens, and secret parameters (e.g., --password=..., Bearer ...)
    - Normalizes path separators (replaces backslashes with forward slashes)
    - Collapses consecutive whitespace
    """
    if not command:
        return ""

    sanitized = command.strip()

    # 1. Redact API tokens, secrets, passwords, and auth parameters
    sanitized = re.sub(
        r"(?i)(--password|--secret|--token|--key|--api[_-]?key)[=\s]+([^\s]+)",
        r"\1 <REDACTED>",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\b(bearer|token|secret|password|api[_-]?key)[\s=:]+([a-zA-Z0-9_\-\.]{8,})",
        r"\1 <REDACTED>",
        sanitized,
    )
    sanitized = re.sub(r"\b(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{30,}\b", "<TOKEN>", sanitized)
    sanitized = re.sub(r"\bsk-[a-zA-Z0-9]{20,}\b", "<TOKEN>", sanitized)

    # 2. Redact user directories in paths (Windows & POSIX)
    sanitized = re.sub(r"(?i)[a-zA-Z]:\\Users\\[^\s\\:\"']+", "<USER_HOME>", sanitized)
    sanitized = re.sub(r"/home/[^\s/:\"']+", "<USER_HOME>", sanitized)
    sanitized = re.sub(r"/Users/[^\s/:\"']+", "<USER_HOME>", sanitized)

    # 3. Normalize Windows path backslashes to forward slashes for arguments
    sanitized = sanitized.replace("\\", "/")

    # 4. Collapse consecutive whitespace
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    return sanitized


def compute_command_signature(command: str) -> Tuple[str, str]:
    """Compute a deterministic signature and display label for a command string.

    Normalization rules:
    - Strips passwords, auth tokens, and user home directories.
    - Normalizes common executable extensions (e.g., .exe, .cmd, .bat).
    - Normalizes relative execution prefixes (e.g., ./, .\\).
    - Preserves material arguments (flags, targets, subcommands) so distinct invocations
      remain distinct (e.g. 'pytest tests/unit' vs 'pytest tests/integration').
    - Normalizes path slashes across operating systems so 'pytest tests\\unit' matches 'pytest tests/unit'.

    Returns:
        (command_signature, command_label)
    """
    sanitized = sanitize_command(command)
    if not sanitized:
        return "cmd_unknown_000000000000", "unknown"

    command_label = sanitized[:256]

    # Split command into executable and args
    tokens = sanitized.split()
    raw_exe = tokens[0] if tokens else "cmd"

    # Normalize executable: strip path down to basename, remove leading ./, strip .exe/.cmd/.bat
    exe_name = raw_exe.split("/")[-1].lower()
    for ext in [".exe", ".cmd", ".bat", ".sh"]:
        if exe_name.endswith(ext):
            exe_name = exe_name[: -len(ext)]
            break

    # Normalize args: lowercase flags, normalize quotes
    norm_tokens = [exe_name]
    for token in tokens[1:]:
        t = token.strip("\"'")
        norm_tokens.append(t)

    normalized_str = " ".join(norm_tokens)

    # Hash the normalized command string
    digest = hashlib.sha256(normalized_str.encode("utf-8")).hexdigest()[:12]
    exe_slug = re.sub(r"[^a-zA-Z0-9_]", "_", exe_name)[:20]

    command_signature = f"cmd_{exe_slug}_{digest}"
    return command_signature, command_label
