from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from devmemory.diagnostics.models import DiagnosticResult, StackFrame
from devmemory.diagnostics.snippets import extract_source_snippet

# Regex for Node.js / V8 error header: e.g. ReferenceError: x is not defined or TypeError: Cannot read property
JS_HEADER_PATTERN = re.compile(
    r"^(?P<type>(?:[A-Za-z]+)?(?:Error|Exception)):\s*(?P<msg>.*)$",
    re.MULTILINE,
)

# Regex for standard V8 stack frame: e.g. "    at Object.test (D:\path\file.js:15:7)" or "    at D:\path\file.ts:10:3"
JS_FRAME_PATTERN = re.compile(
    r"^\s*at\s+(?:(?P<func>[^\(\r\n]+)\s+\()?(?P<file>(?:[A-Za-z]:[\\/]|/|\./|\.\./|[a-zA-Z0-9_\-\./\\]+)[^\:\r\n]+):(?P<line>\d+):(?P<col>\d+)\)?",
    re.MULTILINE,
)

# Regex for Jest/Vitest failed test file line: e.g. "  ● Test suite failed to run ... at src/app.test.js:12:9"
JEST_FRAME_PATTERN = re.compile(
    r"^\s*(?:at\s+)?(?P<file>[a-zA-Z0-9_\-\./\\]+\.(?:js|jsx|ts|tsx|mjs|cjs)):(?P<line>\d+):(?P<col>\d+)",
    re.MULTILINE,
)


def parse_javascript_stack(
    output: str,
    cwd: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> DiagnosticResult:
    """
    Parse Node.js, V8, TypeScript, and Jest/Vitest stack traces from command output.
    Extracts error type, message, stack frames with column offsets, and attaches verified snippets.
    """
    if not output or not output.strip():
        return DiagnosticResult(
            language="javascript",
            error_type="Unknown",
            message="",
            has_diagnostic=False,
        )

    # Search for header e.g. TypeError: Cannot read properties of undefined
    header_match = JS_HEADER_PATTERN.search(output)
    error_type = "JavaScriptError"
    message = ""

    if header_match:
        error_type = header_match.group("type").strip()
        message = header_match.group("msg").strip()
    elif "node:internal" in output or "    at " in output:
        error_type = "NodeRuntimeError"
        message = "Runtime error detected in Node.js execution"

    frames: List[StackFrame] = []
    lines = output.splitlines()

    for line in lines:
        match = JS_FRAME_PATTERN.match(line) or JEST_FRAME_PATTERN.match(line)
        if match:
            raw_file = match.group("file").strip()
            line_num = int(match.group("line"))
            col_num = int(match.group("col"))
            func_name = match.group("func").strip() if "func" in match.groupdict() and match.group("func") else None

            # Clean function name if any
            if func_name and func_name.startswith("async "):
                func_name = func_name[6:]

            snippet = extract_source_snippet(
                file_path_str=raw_file,
                target_line=line_num,
                target_col=col_num,
                cwd=cwd,
                project_root=project_root,
            )

            is_project = (
                snippet.is_safe
                and snippet.error is None
                and not ("node_modules" in raw_file or "node:internal" in raw_file)
            )

            frame = StackFrame(
                raw_frame=line.strip(),
                file_path=raw_file,
                line_number=line_num,
                column_number=col_num,
                function_name=func_name,
                code_line=None,
                is_project_file=is_project,
                snippet=snippet if snippet.lines else None,
            )
            frames.append(frame)

    primary_frame = None
    if frames:
        project_frames = [f for f in frames if f.is_project_file and f.snippet and f.snippet.lines]
        if project_frames:
            primary_frame = project_frames[0]
        else:
            primary_frame = frames[0]

    has_diag = bool(header_match or frames or "    at " in output)
    confidence = 0.9 if (header_match and frames) else (0.6 if has_diag else 0.0)

    return DiagnosticResult(
        language="javascript",
        error_type=error_type,
        message=message,
        frames=frames,
        primary_frame=primary_frame,
        raw_traceback=output.strip(),
        confidence=confidence,
        has_diagnostic=has_diag,
    )
