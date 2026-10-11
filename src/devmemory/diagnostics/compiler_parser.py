from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from devmemory.diagnostics.models import DiagnosticResult, StackFrame
from devmemory.diagnostics.snippets import extract_source_snippet

# Regex for standard compiler line: filename.ext:line:col: error: message or filename.ext:line: error: message
COMPILER_LINE_PATTERN = re.compile(
    r"^(?P<file>(?:[a-zA-Z]:[\\/])?[a-zA-Z0-9_\-\./\\]+\.(?:java|c|cpp|cc|cxx|h|hpp|rs|go|kt|scala)):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?:(?P<severity>error|fatal error|warning):\s*)?(?P<msg>[^\r\n]+)$",
    re.MULTILINE | re.IGNORECASE,
)

# Regex for MSVC compiler line: filename.ext(line): error Cxxxx: message
MSVC_LINE_PATTERN = re.compile(
    r"^(?P<file>(?:[a-zA-Z]:[\\/])?[a-zA-Z0-9_\-\./\\]+\.(?:c|cpp|cc|cxx|h|hpp))\((?P<line>\d+)(?:,\s*(?P<col>\d+))?\):\s*(?P<severity>error|warning)\s*(?:[A-Z0-9]+)?:\s*(?P<msg>[^\r\n]+)$",
    re.MULTILINE | re.IGNORECASE,
)

# Regexes for missing command/executable
CMD_NOT_FOUND_PATTERNS = [
    re.compile(r"['\"]?([a-zA-Z0-9_\-\.]+)['\"]?\s+is not recognized as an internal or external command", re.IGNORECASE),
    re.compile(r"The term ['\"]?([a-zA-Z0-9_\-\.]+)['\"]?\s+is not recognized as the name of a cmdlet", re.IGNORECASE),
    re.compile(r"(?:bash|sh|zsh):\s*([a-zA-Z0-9_\-\.]+):\s*command not found", re.IGNORECASE),
    re.compile(r"(?:^|\n)([a-zA-Z0-9_\-\.]+):\s*command not found", re.IGNORECASE),
    re.compile(r"exec:\s*[\"']?([a-zA-Z0-9_\-\.]+)[\"']?:\s*executable file not found", re.IGNORECASE),
]

# Regexes for missing file errors
FILE_NOT_FOUND_PATTERNS = [
    re.compile(r"error:\s*file not found:\s*([^\r\n]+)", re.IGNORECASE),
    re.compile(r"(?:gcc|clang|javac|java):\s*error:\s*([^\r\n]+?):\s*No such file or directory", re.IGNORECASE),
    re.compile(r"can't open file ['\"]?([^'\"\r\n]+)['\"]?:\s*\[Errno 2\] No such file or directory", re.IGNORECASE),
]


def parse_compiler_output(
    output: str,
    cwd: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> DiagnosticResult:
    """
    Parse structured compiler diagnostics (Java, GCC, Clang, MSVC) and execution failures.
    Extracts filename, line number, column offset, caret pointer, and source snippets.
    """
    if not output or not output.strip():
        return DiagnosticResult(
            language="unknown",
            error_type="Unknown",
            message="",
            has_diagnostic=False,
        )

    lines = output.splitlines()

    # 1. Search for standard compiler error line (e.g. test_failure.java:2: error: '{' expected)
    for i, line in enumerate(lines):
        match = COMPILER_LINE_PATTERN.match(line.strip()) or MSVC_LINE_PATTERN.match(line.strip())
        if match:
            raw_file = match.group("file").strip()
            line_num = int(match.group("line"))
            col_num = int(match.group("col")) if match.group("col") else None
            msg = match.group("msg").strip()
            severity = match.group("severity") or "error"

            # Check next lines for source line and caret pointer (e.g. ^)
            code_line: Optional[str] = None
            if i + 1 < len(lines):
                candidate_line = lines[i + 1]
                if not candidate_line.startswith("error:") and not COMPILER_LINE_PATTERN.match(candidate_line.strip()):
                    code_line = candidate_line.strip()
                    # Check i + 2 for caret
                    if i + 2 < len(lines):
                        pointer_line = lines[i + 2]
                        if "^" in pointer_line:
                            caret_col = pointer_line.find("^") + 1
                            if col_num is None:
                                col_num = caret_col

            # Extract snippet from filesystem
            snippet = extract_source_snippet(
                file_path_str=raw_file,
                target_line=line_num,
                target_col=col_num,
                cwd=cwd,
                project_root=project_root,
            )

            # Determine language
            lang = "compiler"
            ext = Path(raw_file).suffix.lower()
            if ext == ".java":
                lang = "java"
            elif ext in (".c", ".h"):
                lang = "c"
            elif ext in (".cpp", ".cc", ".cxx", ".hpp"):
                lang = "cpp"
            elif ext == ".rs":
                lang = "rust"
            elif ext == ".go":
                lang = "go"

            frame = StackFrame(
                raw_frame=line.strip(),
                file_path=raw_file,
                line_number=line_num,
                column_number=col_num,
                code_line=code_line,
                snippet=snippet,
                is_project_file=snippet.is_safe,
            )

            return DiagnosticResult(
                language=lang,
                error_type="CompilationError",
                message=msg,
                frames=[frame],
                primary_frame=frame,
                raw_traceback=output.strip(),
                confidence=0.95,
                has_diagnostic=True,
            )

    # 2. Check for missing executable / command not found
    for pat in CMD_NOT_FOUND_PATTERNS:
        m = pat.search(output)
        if m:
            cmd_name = m.group(1).strip()
            return DiagnosticResult(
                language="command",
                error_type="CommandNotFoundError",
                message=f"Executable '{cmd_name}' not found on system PATH",
                raw_traceback=output.strip(),
                confidence=0.90,
                has_diagnostic=True,
            )

    # 3. Check for missing source file
    for pat in FILE_NOT_FOUND_PATTERNS:
        m = pat.search(output)
        if m:
            missing_file = m.group(1).strip()
            return DiagnosticResult(
                language="system",
                error_type="FileNotFoundError",
                message=f"Source file '{missing_file}' not found",
                raw_traceback=output.strip(),
                confidence=0.90,
                has_diagnostic=True,
            )

    # 4. Check for generic compilation summary (e.g. error: compilation failed or 1 error)
    if "error: compilation failed" in output.lower() or "compilation terminated" in output.lower():
        return DiagnosticResult(
            language="compiler",
            error_type="CompilationError",
            message="Compilation failed",
            raw_traceback=output.strip(),
            confidence=0.75,
            has_diagnostic=True,
        )

    return DiagnosticResult(
        language="unknown",
        error_type="UnrecognizedError",
        message="No supported compiler diagnostic detected in command output",
        has_diagnostic=False,
    )
