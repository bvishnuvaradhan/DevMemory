from __future__ import annotations

from pathlib import Path
from typing import Optional

from devmemory.diagnostics.javascript_parser import parse_javascript_stack
from devmemory.diagnostics.models import DiagnosticResult, SourceSnippet, StackFrame
from devmemory.diagnostics.python_parser import parse_python_traceback
from devmemory.diagnostics.snippets import extract_source_snippet


def analyze_error_output(
    stdout: str,
    stderr: str,
    cwd: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> DiagnosticResult:
    """
    Unified entry point for error diagnosis.
    Inspects stderr and stdout, detects the language/runtime format,
    and returns a structured DiagnosticResult with verified snippets.
    """
    combined = f"{stderr}\n{stdout}".strip()
    if not combined:
        return DiagnosticResult(
            language="unknown",
            error_type="Unknown",
            message="No output captured",
            has_diagnostic=False,
        )

    # Detect Python first (Traceback, Python exceptions, .py filenames)
    py_diag = parse_python_traceback(combined, cwd=cwd, project_root=project_root)
    if py_diag.has_diagnostic and py_diag.confidence >= 0.5:
        return py_diag

    # Detect JavaScript/TypeScript (Node stack traces, .js/.ts filenames)
    js_diag = parse_javascript_stack(combined, cwd=cwd, project_root=project_root)
    if js_diag.has_diagnostic and js_diag.confidence >= 0.5:
        return js_diag

    # Fallback if Python or JS had weak matches
    if py_diag.has_diagnostic:
        return py_diag
    if js_diag.has_diagnostic:
        return js_diag

    return DiagnosticResult(
        language="unknown",
        error_type="UnrecognizedError",
        message="No supported stack trace detected in command output",
        has_diagnostic=False,
    )


__all__ = [
    "DiagnosticResult",
    "StackFrame",
    "SourceSnippet",
    "extract_source_snippet",
    "parse_python_traceback",
    "parse_javascript_stack",
    "analyze_error_output",
]
