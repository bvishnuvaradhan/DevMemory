from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from devmemory.diagnostics.models import SourceSnippet

MAX_SNIPPET_FILE_SIZE_BYTES = 1024 * 1024  # 1 MB maximum file size to read
DEFAULT_CONTEXT_WINDOW = 5  # 5 lines before and after target line


def is_path_safe_under_root(target_path: Path, root_path: Path) -> bool:
    """
    Ensure the resolved canonical path is strictly contained within the resolved root path,
    preventing directory traversal attacks or symlink escapes.
    """
    try:
        resolved_target = target_path.resolve()
        resolved_root = root_path.resolve()
        # Check if resolved_target starts with resolved_root
        return resolved_target == resolved_root or resolved_root in resolved_target.parents
    except Exception:
        return False


def extract_source_snippet(
    file_path_str: str,
    target_line: int,
    target_col: Optional[int] = None,
    cwd: Optional[Path] = None,
    project_root: Optional[Path] = None,
    context_lines: int = DEFAULT_CONTEXT_WINDOW,
) -> SourceSnippet:
    """
    Safely extract a source code snippet around the target line from the local filesystem.
    Validates existence, path traversal, file size, line boundaries, and encoding.
    """
    resolved_cwd = cwd.resolve() if cwd else Path.cwd().resolve()
    resolved_root = project_root.resolve() if project_root else resolved_cwd

    raw_path = Path(file_path_str)
    if not raw_path.is_absolute():
        candidate_path = resolved_cwd / raw_path
    else:
        candidate_path = raw_path

    # Path traversal and existence checks
    if not candidate_path.exists():
        return SourceSnippet(
            file_path=file_path_str,
            target_line=target_line,
            target_col=target_col,
            start_line=target_line,
            end_line=target_line,
            lines=[],
            is_safe=False,
            error=f"File does not exist: {file_path_str}",
        )

    if not candidate_path.is_file():
        return SourceSnippet(
            file_path=file_path_str,
            target_line=target_line,
            target_col=target_col,
            start_line=target_line,
            end_line=target_line,
            lines=[],
            is_safe=False,
            error=f"Path is not a regular file: {file_path_str}",
        )

    # Validate containment under project root
    if not is_path_safe_under_root(candidate_path, resolved_root):
        return SourceSnippet(
            file_path=file_path_str,
            target_line=target_line,
            target_col=target_col,
            start_line=target_line,
            end_line=target_line,
            lines=[],
            is_safe=False,
            error=f"Path traversal rejected: '{file_path_str}' is outside project root '{resolved_root}'",
        )

    # Check file size limit
    try:
        file_size = candidate_path.stat().st_size
        if file_size > MAX_SNIPPET_FILE_SIZE_BYTES:
            return SourceSnippet(
                file_path=str(candidate_path.resolve()),
                target_line=target_line,
                target_col=target_col,
                start_line=target_line,
                end_line=target_line,
                lines=[],
                is_safe=False,
                error=f"File size ({file_size} bytes) exceeds maximum limit ({MAX_SNIPPET_FILE_SIZE_BYTES} bytes)",
            )
    except OSError as exc:
        return SourceSnippet(
            file_path=file_path_str,
            target_line=target_line,
            target_col=target_col,
            start_line=target_line,
            end_line=target_line,
            lines=[],
            is_safe=False,
            error=f"Cannot inspect file metadata: {exc}",
        )

    # Read lines safely with UTF-8 fallback
    try:
        with open(candidate_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except Exception as exc:
        return SourceSnippet(
            file_path=str(candidate_path.resolve()),
            target_line=target_line,
            target_col=target_col,
            start_line=target_line,
            end_line=target_line,
            lines=[],
            is_safe=False,
            error=f"Failed to read file: {exc}",
        )

    total_lines = len(all_lines)
    if total_lines == 0:
        return SourceSnippet(
            file_path=str(candidate_path.resolve()),
            target_line=target_line,
            target_col=target_col,
            start_line=1,
            end_line=1,
            lines=[],
            is_safe=True,
            error="File is empty",
        )

    if target_line < 1 or target_line > total_lines:
        return SourceSnippet(
            file_path=str(candidate_path.resolve()),
            target_line=target_line,
            target_col=target_col,
            start_line=target_line,
            end_line=target_line,
            lines=[],
            is_safe=False,
            error=f"Target line {target_line} out of range (file has {total_lines} lines)",
        )

    start_idx = max(0, target_line - 1 - context_lines)
    end_idx = min(total_lines, target_line + context_lines)

    extracted = [line.rstrip("\r\n") for line in all_lines[start_idx:end_idx]]

    return SourceSnippet(
        file_path=str(candidate_path.resolve()),
        target_line=target_line,
        target_col=target_col,
        start_line=start_idx + 1,
        end_line=end_idx,
        lines=extracted,
        is_safe=True,
        error=None,
    )
