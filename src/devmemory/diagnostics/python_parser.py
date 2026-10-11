from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from devmemory.diagnostics.models import DiagnosticResult, StackFrame
from devmemory.diagnostics.snippets import extract_source_snippet

# Regex to match Python standard stack frame: File ".../path.py", line 123, in func_name
FRAME_PATTERN = re.compile(
    r'^\s*File\s+"(?P<file>[^"]+)",\s+line\s+(?P<line>\d+)(?:,\s+in\s+(?P<func>.+))?',
    re.MULTILINE,
)

# Regex to match Python standard exception line: e.g. TypeError: 'NoneType' object is not subscriptable
EXCEPTION_PATTERN = re.compile(
    r"^(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning|Exit|Interrupt|Fault|Notice)):\s*(?P<msg>.*)$",
    re.MULTILINE,
)

# Regex to match SyntaxError specific line/col indicators: e.g. File "foo.py", line 1
SYNTAX_PATTERN = re.compile(
    r'^\s*File\s+"(?P<file>[^"]+)",\s+line\s+(?P<line>\d+)(?:\r?\n(?P<code_line>.*)\r?\n\s*(?P<pointer>\^+))?',
    re.MULTILINE,
)


def parse_python_traceback(
    output: str,
    cwd: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> DiagnosticResult:
    """
    Parse Python tracebacks and syntax errors from command output.
    Extracts exception type, message, stack frames, line numbers, and attaches verified snippets.
    """
    if not output or not output.strip():
        return DiagnosticResult(
            language="python",
            error_type="Unknown",
            message="",
            has_diagnostic=False,
        )

    # Search for exception type and message
    exception_matches = list(EXCEPTION_PATTERN.finditer(output))
    error_type = "PythonError"
    message = ""
    raw_tb = ""

    if exception_matches:
        last_exc = exception_matches[-1]
        error_type = last_exc.group("type").strip()
        message = last_exc.group("msg").strip()
    elif "Traceback (most recent call last):" in output:
        # Traceback header present without standard Exception line (e.g. truncated)
        error_type = "Traceback"
        message = "Traceback detected without trailing exception message"

    # Identify traceback boundaries
    tb_header_idx = output.rfind("Traceback (most recent call last):")
    if tb_header_idx != -1:
        raw_tb = output[tb_header_idx:].strip()
    else:
        # Could be a SyntaxError without "Traceback (most recent call last):"
        if "SyntaxError" in output or "IndentationError" in output:
            raw_tb = output.strip()

    # Parse individual frames
    frames: List[StackFrame] = []
    lines = output.splitlines()

    for i, line in enumerate(lines):
        match = FRAME_PATTERN.match(line)
        if match:
            file_path = match.group("file")
            line_num = int(match.group("line"))
            func_name = match.group("func").strip() if match.group("func") else None

            # Attempt to grab the accompanying source code line below the File header
            code_line = None
            if i + 1 < len(lines) and lines[i + 1].startswith("    "):
                code_line = lines[i + 1].strip()

            snippet = extract_source_snippet(
                file_path_str=file_path,
                target_line=line_num,
                cwd=cwd,
                project_root=project_root,
            )

            is_project = snippet.is_safe and snippet.error is None and not ("site-packages" in file_path or "lib/python" in file_path)

            frame = StackFrame(
                raw_frame=line.strip(),
                file_path=file_path,
                line_number=line_num,
                function_name=func_name,
                code_line=code_line,
                is_project_file=is_project,
                snippet=snippet if snippet.lines else None,
            )
            frames.append(frame)

    if not frames and ("SyntaxError" in error_type or "IndentationError" in error_type):
        # Handle standalone SyntaxError with line indicator
        syntax_match = SYNTAX_PATTERN.search(output)
        if syntax_match:
            file_path = syntax_match.group("file")
            line_num = int(syntax_match.group("line"))
            code_line = syntax_match.group("code_line")
            col = None
            pointer = syntax_match.group("pointer")
            if pointer and code_line:
                col = len(pointer)

            snippet = extract_source_snippet(
                file_path_str=file_path,
                target_line=line_num,
                target_col=col,
                cwd=cwd,
                project_root=project_root,
            )

            frame = StackFrame(
                raw_frame=syntax_match.group(0).strip(),
                file_path=file_path,
                line_number=line_num,
                column_number=col,
                function_name="<module>",
                code_line=code_line.strip() if code_line else None,
                is_project_file=snippet.is_safe and snippet.error is None,
                snippet=snippet if snippet.lines else None,
            )
            frames.append(frame)

    # Determine primary frame: prefer project files from bottom up, else the last frame
    primary_frame = None
    if frames:
        project_frames = [f for f in frames if f.is_project_file and f.snippet and f.snippet.lines]
        if project_frames:
            primary_frame = project_frames[-1]
        else:
            primary_frame = frames[-1]

    # Confidence calculation: require traceback or python-specific frames
    has_tb = "Traceback (most recent call last):" in output or "SyntaxError" in output or "IndentationError" in output
    has_diag = bool((has_tb and (exception_matches or frames)) or (frames and exception_matches))
    
    # If Node.js 'at ...' frames are detected without python frames, do not claim high confidence
    if "    at " in output and not frames:
        confidence = 0.0
        has_diag = False
    elif has_tb and frames and exception_matches:
        confidence = 0.95
    elif frames and exception_matches:
        confidence = 0.85
    elif has_tb or frames:
        confidence = 0.5
    else:
        confidence = 0.2 if exception_matches else 0.0

    return DiagnosticResult(
        language="python",
        error_type=error_type,
        message=message,
        frames=frames,
        primary_frame=primary_frame,
        raw_traceback=raw_tb,
        confidence=confidence,
        has_diagnostic=has_diag,
    )
