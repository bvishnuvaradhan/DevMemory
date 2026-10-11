from pathlib import Path
from unittest.mock import patch

import pytest

from devmemory.diagnostics.javascript_parser import parse_javascript_stack
from devmemory.diagnostics.models import DiagnosticResult, SourceSnippet
from devmemory.diagnostics.python_parser import parse_python_traceback
from devmemory.diagnostics.snippets import extract_source_snippet, is_path_safe_under_root
from devmemory.diagnostics import analyze_error_output


# ---------------------------------------------------------------------------
# Python Traceback Tests
# ---------------------------------------------------------------------------

def test_parse_standard_python_type_error(tmp_path: Path):
    """Test parsing a standard Python TypeError with stack frames and source snippet."""
    app_file = tmp_path / "app.py"
    app_file.write_text(
        "def compute(val):\n"
        "    return val + 10\n\n"
        "def main():\n"
        "    compute(None)\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n",
        encoding="utf-8",
    )

    sample_traceback = (
        'Traceback (most recent call last):\n'
        f'  File "{app_file}", line 8, in <module>\n'
        '    main()\n'
        f'  File "{app_file}", line 5, in main\n'
        '    compute(None)\n'
        f'  File "{app_file}", line 2, in compute\n'
        '    return val + 10\n'
        "TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'\n"
    )

    diag = parse_python_traceback(sample_traceback, cwd=tmp_path, project_root=tmp_path)
    assert diag.has_diagnostic is True
    assert diag.language == "python"
    assert diag.error_type == "TypeError"
    assert "unsupported operand type" in diag.message
    assert len(diag.frames) == 3
    assert diag.primary_frame is not None
    assert diag.primary_frame.line_number == 2
    assert diag.primary_frame.snippet is not None
    assert "return val + 10" in "\n".join(diag.primary_frame.snippet.lines)


def test_parse_python_syntax_error(tmp_path: Path):
    """Test parsing a Python SyntaxError with line indicator."""
    broken_file = tmp_path / "syntax_err.py"
    broken_file.write_text("def test(\n    print('missing paren'\n", encoding="utf-8")

    sample_syntax_err = (
        f'  File "{broken_file}", line 2\n'
        "    print('missing paren'\n"
        "                         ^\n"
        "SyntaxError: '(' was never closed\n"
    )

    diag = parse_python_traceback(sample_syntax_err, cwd=tmp_path, project_root=tmp_path)
    assert diag.has_diagnostic is True
    assert diag.error_type == "SyntaxError"
    assert "never closed" in diag.message
    assert diag.primary_frame is not None
    assert diag.primary_frame.line_number == 2


def test_parse_truncated_python_traceback():
    """Test handling of truncated or incomplete tracebacks."""
    incomplete_output = "Traceback (most recent call last):\n  File \"unknown.py\", line 10\n"
    diag = parse_python_traceback(incomplete_output)
    assert diag.has_diagnostic is True
    assert diag.language == "python"
    assert len(diag.frames) == 1
    assert diag.frames[0].line_number == 10


# ---------------------------------------------------------------------------
# JavaScript / TypeScript Stack Tests
# ---------------------------------------------------------------------------

def test_parse_javascript_type_error(tmp_path: Path):
    """Test parsing Node.js / V8 TypeError stack trace."""
    js_file = tmp_path / "server.js"
    js_file.write_text(
        "function handleRequest(req) {\n"
        "    return req.user.name;\n"
        "}\n"
        "handleRequest({});\n",
        encoding="utf-8",
    )

    sample_node_err = (
        f"{js_file}:2\n"
        "    return req.user.name;\n"
        "                    ^\n\n"
        "TypeError: Cannot read properties of undefined (reading 'name')\n"
        f"    at handleRequest ({js_file}:2:21)\n"
        f"    at Object.<anonymous> ({js_file}:4:1)\n"
        "    at Module._compile (node:internal/modules/cjs/loader:1565:14)\n"
    )

    diag = parse_javascript_stack(sample_node_err, cwd=tmp_path, project_root=tmp_path)
    assert diag.has_diagnostic is True
    assert diag.language == "javascript"
    assert diag.error_type == "TypeError"
    assert "Cannot read properties of undefined" in diag.message
    assert len(diag.frames) >= 2
    assert diag.primary_frame is not None
    assert diag.primary_frame.line_number == 2
    assert diag.primary_frame.column_number == 21
    assert diag.primary_frame.snippet is not None
    assert "return req.user.name" in "\n".join(diag.primary_frame.snippet.lines)


def test_parse_anonymous_javascript_frame():
    """Test parsing anonymous V8 frames."""
    raw_stack = (
        "ReferenceError: config is not defined\n"
        "    at src/index.ts:15:3\n"
    )
    diag = parse_javascript_stack(raw_stack)
    assert diag.has_diagnostic is True
    assert diag.error_type == "ReferenceError"
    assert len(diag.frames) == 1
    assert diag.frames[0].file_path == "src/index.ts"
    assert diag.frames[0].line_number == 15
    assert diag.frames[0].column_number == 3


# ---------------------------------------------------------------------------
# Safe Snippet Extraction & Security Tests
# ---------------------------------------------------------------------------

def test_snippet_valid_extraction(tmp_path: Path):
    """Test standard 5-line window extraction around target line."""
    test_file = tmp_path / "module.py"
    lines = [f"line {i}" for i in range(1, 21)]
    test_file.write_text("\n".join(lines), encoding="utf-8")

    snip = extract_source_snippet(
        file_path_str=str(test_file),
        target_line=10,
        project_root=tmp_path,
        context_lines=3,
    )
    assert snip.is_safe is True
    assert snip.error is None
    assert snip.start_line == 7
    assert snip.end_line == 13
    assert len(snip.lines) == 7
    assert "line 10" in snip.lines[3]


def test_snippet_missing_file(tmp_path: Path):
    """Test graceful handling when target file does not exist."""
    snip = extract_source_snippet(
        file_path_str=str(tmp_path / "missing.py"),
        target_line=5,
        project_root=tmp_path,
    )
    assert snip.is_safe is False
    assert "does not exist" in snip.error


def test_snippet_out_of_range_line(tmp_path: Path):
    """Test line number exceeding file length."""
    small_file = tmp_path / "small.py"
    small_file.write_text("line 1\nline 2\n", encoding="utf-8")

    snip = extract_source_snippet(
        file_path_str=str(small_file),
        target_line=999,
        project_root=tmp_path,
    )
    assert snip.is_safe is False
    assert "out of range" in snip.error


def test_snippet_rejects_directory_traversal(tmp_path: Path):
    """Test that path attempting to escape project root via ../ is rejected."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    outside_file = tmp_path / "outside_secret.py"
    outside_file.write_text("SECRET_KEY = 'secret'", encoding="utf-8")

    snip = extract_source_snippet(
        file_path_str=str(outside_file),
        target_line=1,
        project_root=project_dir,
    )
    assert snip.is_safe is False
    assert "traversal rejected" in snip.error.lower()


def test_snippet_rejects_large_files(tmp_path: Path):
    """Test that files exceeding size limits are safely bounded and rejected."""
    large_file = tmp_path / "large.py"
    # Write 2 MB file
    large_file.write_bytes(b"A" * (2 * 1024 * 1024))

    snip = extract_source_snippet(
        file_path_str=str(large_file),
        target_line=1,
        project_root=tmp_path,
    )
    assert snip.is_safe is False
    assert "exceeds maximum limit" in snip.error


# ---------------------------------------------------------------------------
# Unified Error Analyzer Tests
# ---------------------------------------------------------------------------

def test_analyze_error_output_clean_output():
    """Test analyze_error_output returns clean result when no errors exist."""
    diag = analyze_error_output(stdout="All tests passed", stderr="")
    assert diag.has_diagnostic is False


def test_analyze_error_output_python_detection(tmp_path: Path):
    """Test automatic language detection for Python output."""
    stderr = "Traceback (most recent call last):\n  File \"calc.py\", line 4\nZeroDivisionError: division by zero"
    diag = analyze_error_output(stdout="", stderr=stderr, cwd=tmp_path)
    assert diag.has_diagnostic is True
    assert diag.language == "python"
    assert diag.error_type == "ZeroDivisionError"
