"""Tests for compiler error diagnostics, non-Python runtime failures, and RootCauseAnalyzer refinement.

Validates:
1. Exact Java compiler error reproduction ('{' expected on class Hello(){) and Requirement 3 accuracy.
2. Java compiler error variations ('{' expected, ';' expected, cannot find symbol, public class mismatch).
3. C/C++ GCC, Clang, and MSVC diagnostic parsing, column/caret extraction, and root cause refinement.
4. Missing executables (Windows cmd, PowerShell, bash) detected as CommandNotFoundError.
5. Missing source files detected as FileNotFoundError.
6. Safe incident derivation in run_service on non-zero exit codes.
7. Safe handling of malformed or noisy compiler output.
8. CLI rendering for compiler error diagnoses and unavailable diagnosis notices.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from rich.console import Console

import sys
from pathlib import Path

# Ensure server module can be imported
server_dir = Path(__file__).resolve().parent.parent / "server"
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from devmemory.diagnostics.compiler_parser import parse_compiler_output
from devmemory.diagnostics import analyze_error_output
from devmemory.cli.main import (
    _convert_diagnostic_to_backend_context,
    _render_backend_report,
)
from devmemory.integration.client import IngestionResult
from devmemory.integration.models import (
    BackendDiagnosisResponse,
    SimilarIncidentMatch,
)
from app.schemas.run import RunCreate, ErrorContext as ServiceErrorContext
from app.services.root_cause_analyzer import refine_root_cause_diagnosis
from app.services.run_service import ingest_run


def _capture_render(ingestion: IngestionResult) -> str:
    """Helper to capture CLI _render_backend_report output."""
    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=False, width=120)
    with patch("devmemory.cli.main.console", test_console):
        _render_backend_report(ingestion)
    return buf.getvalue()


# ==============================================================================
# 1. Exact Java Compiler Error Reproduction & Requirement 3 Accuracy
# ==============================================================================

def test_exact_java_compiler_error_reproduction_and_requirement_3_accuracy():
    """Verify exact Java error parsing and Requirement 3 probable cause and fix."""
    raw_java_output = (
        "test_failure.java:2: error: '{' expected\n"
        "class Hello(){\n"
        "          ^\n"
        "1 error\n"
        "error: compilation failed\n"
    )

    # 1. Parsing verification
    diag = parse_compiler_output(raw_java_output)
    assert diag.has_diagnostic is True
    assert diag.language == "java"
    assert diag.error_type == "CompilationError"
    assert diag.message == "'{' expected"
    assert diag.primary_frame is not None
    assert diag.primary_frame.file_path == "test_failure.java"
    assert diag.primary_frame.line_number == 2
    assert diag.primary_frame.column_number == 11
    assert diag.primary_frame.code_line == "class Hello(){"

    # 2. Root cause refinement verification (Requirement 3)
    refined = refine_root_cause_diagnosis(
        error_type=diag.error_type,
        error_message=diag.message,
        source_snippet=diag.primary_frame.code_line,
        stack_trace=raw_java_output,
        file_path=diag.primary_frame.file_path,
        line=diag.primary_frame.line_number,
        column=diag.primary_frame.column_number,
    )

    assert refined.is_refined is True
    # Probable Cause must explain parentheses after class name and brace expectation
    assert "The Java class declaration contains parentheses after the class name." in refined.likely_cause
    assert "Java class declarations use braces to delimit the class body, so the compiler expects '{' after Hello." in refined.likely_cause

    # Suggested Fix must contain:
    # - Change 'class Hello(){' to 'class Hello {'
    # - Keep methods/fields inside class body
    # - Re-run after correcting
    assert any("Change 'class Hello(){' to 'class Hello {'" in step for step in refined.suggested_steps)
    assert any("Keep methods and fields inside the class body." in step for step in refined.suggested_steps)
    assert any("Re-run the Java source file after correcting the declaration." in step for step in refined.suggested_steps)


def test_java_compiler_error_variations():
    """Verify general Java compiler error diagnostics: '{' expected, ';' expected, cannot find symbol, class mismatch."""
    # Case A: General '{' expected (e.g. method declaration)
    refined_brace = refine_root_cause_diagnosis(
        error_type="CompilationError",
        error_message="'{' expected",
        source_snippet="public void execute()",
        stack_trace="Service.java:15: error: '{' expected\npublic void execute()\n                     ^",
        file_path="Service.java",
        line=15,
        column=22,
    )
    assert refined_brace.is_refined is True
    assert "opening brace" in refined_brace.likely_cause
    assert any("opening brace '{'" in s for s in refined_brace.suggested_steps)

    # Case B: ';' expected
    refined_semi = refine_root_cause_diagnosis(
        error_type="CompilationError",
        error_message="';' expected",
        source_snippet="int count = 100",
        stack_trace="Service.java:20: error: ';' expected\nint count = 100\n               ^",
        file_path="Service.java",
        line=20,
    )
    assert refined_semi.is_refined is True
    assert "missing a terminating semicolon ';'" in refined_semi.likely_cause
    assert any("terminating semicolon ';'" in s for s in refined_semi.suggested_steps)

    # Case C: cannot find symbol
    refined_symbol = refine_root_cause_diagnosis(
        error_type="CompilationError",
        error_message="cannot find symbol",
        source_snippet="logger.info(data);",
        stack_trace="Service.java:25: error: cannot find symbol\n  symbol:   variable logger\n  location: class Service",
        file_path="Service.java",
        line=25,
    )
    assert refined_symbol.is_refined is True
    assert "identifier 'logger' cannot be resolved" in refined_symbol.likely_cause
    assert any("import" in s for s in refined_symbol.suggested_steps)

    # Case D: Public class file name mismatch
    refined_pub = refine_root_cause_diagnosis(
        error_type="CompilationError",
        error_message="class Greeter is public, should be declared in a file named Greeter.java",
        source_snippet="public class Greeter {",
        stack_trace="Main.java:1: error: class Greeter is public, should be declared in a file named Greeter.java",
        file_path="Main.java",
        line=1,
    )
    assert refined_pub.is_refined is True
    assert "public class 'Greeter' must be declared in a file named 'Greeter.java'" in refined_pub.likely_cause
    assert any("Rename the source file" in s for s in refined_pub.suggested_steps)


# ==============================================================================
# 2. C/C++ GCC, Clang, and MSVC Diagnostics
# ==============================================================================

def test_gcc_clang_compiler_diagnostic_parsing_and_refinement():
    """Verify GCC/Clang output parsing and root cause refinement."""
    # Case A: Syntax error with line and column
    gcc_output = (
        "src/calc.c:5:10: error: expected ';' before 'return'\n"
        "    int a = 5\n"
        "         ^\n"
    )
    diag = parse_compiler_output(gcc_output)
    assert diag.has_diagnostic is True
    assert diag.language == "c"
    assert diag.error_type == "CompilationError"
    assert diag.primary_frame.file_path == "src/calc.c"
    assert diag.primary_frame.line_number == 5
    assert diag.primary_frame.column_number == 10

    # Case B: Missing header (fatal error)
    header_output = (
        "src/main.c:2:10: fatal error: non_existent_header.h: No such file or directory\n"
        " #include <non_existent_header.h>\n"
        "          ^~~~~~~~~~~~~~~~~~~~~~~\n"
        "compilation terminated.\n"
    )
    diag_h = parse_compiler_output(header_output)
    assert diag_h.has_diagnostic is True
    assert diag_h.primary_frame.line_number == 2
    refined_h = refine_root_cause_diagnosis(
        error_type=diag_h.error_type,
        error_message=diag_h.message,
        stack_trace=header_output,
        file_path="src/main.c",
        line=2,
    )
    assert refined_h.is_refined is True
    assert "header file 'non_existent_header.h' referenced in the #include directive was not found" in refined_h.likely_cause
    assert any("-I<path>" in s for s in refined_h.suggested_steps)

    # Case C: Undeclared identifier
    undeclared_output = "engine.cpp:42:5: error: 'target_value' was not declared in this scope"
    refined_u = refine_root_cause_diagnosis(
        error_type="CompilationError",
        error_message="'target_value' was not declared in this scope",
        stack_trace=undeclared_output,
        file_path="engine.cpp",
        line=42,
    )
    assert refined_u.is_refined is True
    assert "identifier 'target_value' was referenced before being declared" in refined_u.likely_cause

    # Case D: Linker error (undefined reference)
    linker_output = "/usr/bin/ld: main.o: in function `main':\nmain.c:(.text+0x15): undefined reference to `calculate_checksum'\ncollect2: error: ld returned 1 exit status"
    refined_ld = refine_root_cause_diagnosis(
        error_type="CompilationError",
        error_message="undefined reference to calculate_checksum",
        stack_trace=linker_output,
        file_path="main.c",
    )
    assert refined_ld.is_refined is True
    assert "definition for 'calculate_checksum' was not found during linking" in refined_ld.likely_cause
    assert any("definition of 'calculate_checksum'" in s for s in refined_ld.suggested_steps)


def test_msvc_compiler_diagnostic_parsing():
    """Verify MSVC compiler diagnostic parsing (file(line,col): error Cxxxx: message)."""
    msvc_output = "D:\\code\\module.cpp(88,12): error C2065: 'counter': undeclared identifier"
    diag = parse_compiler_output(msvc_output)
    assert diag.has_diagnostic is True
    assert diag.language == "cpp"
    assert diag.primary_frame.line_number == 88
    assert diag.primary_frame.column_number == 12
    assert "undeclared identifier" in diag.message


# ==============================================================================
# 3. Missing Executables and Missing Files
# ==============================================================================

def test_missing_compiler_executable_detection():
    """Verify missing compiler or runtime executables produce CommandNotFoundError with helpful advice."""
    # Windows cmd
    cmd_out = "'javac' is not recognized as an internal or external command, operable program or batch file."
    diag_cmd = parse_compiler_output(cmd_out)
    assert diag_cmd.has_diagnostic is True
    assert diag_cmd.error_type == "CommandNotFoundError"
    assert "javac" in diag_cmd.message

    # PowerShell
    ps_out = "The term 'gcc' is not recognized as the name of a cmdlet, function, script file, or operable program."
    diag_ps = parse_compiler_output(ps_out)
    assert diag_ps.has_diagnostic is True
    assert diag_ps.error_type == "CommandNotFoundError"
    assert "gcc" in diag_ps.message

    # Bash / POSIX
    sh_out = "bash: clang: command not found"
    diag_sh = parse_compiler_output(sh_out)
    assert diag_sh.has_diagnostic is True
    assert diag_sh.error_type == "CommandNotFoundError"
    assert "clang" in diag_sh.message

    # Refinement test
    refined = refine_root_cause_diagnosis(
        error_type=diag_cmd.error_type,
        error_message=diag_cmd.message,
        stack_trace=cmd_out,
    )
    assert refined.is_refined is True
    assert "command 'javac' was not found" in refined.likely_cause
    assert any("PATH environment variable" in s for s in refined.suggested_steps)


def test_missing_source_file_detection():
    """Verify missing source file error parsing and refinement."""
    raw = "error: file not found: test_missing.java"
    diag = parse_compiler_output(raw)
    assert diag.has_diagnostic is True
    assert diag.error_type == "FileNotFoundError"
    assert "test_missing.java" in diag.message

    refined = refine_root_cause_diagnosis(
        error_type=diag.error_type,
        error_message=diag.message,
    )
    assert refined.is_refined is True
    assert "source file 'test_missing.java' does not exist" in refined.likely_cause
    assert any("expected working directory" in s for s in refined.suggested_steps)


# ==============================================================================
# 4. Fallback Incident Derivation and Safe Error Handling
# ==============================================================================

def test_backend_context_conversion_fallback():
    """Verify _convert_diagnostic_to_backend_context creates a fallback context when diagnostic is missing."""
    # Case A: None diagnostic with non-zero exit code fallback message
    ctx = _convert_diagnostic_to_backend_context(None, fallback_message="Process terminated with exit code 1")
    assert ctx is not None
    assert ctx.error_type == "CommandError"
    assert ctx.message == "Process terminated with exit code 1"

    # Case B: None diagnostic and no fallback message
    ctx_empty = _convert_diagnostic_to_backend_context(None, fallback_message=None)
    assert ctx_empty is None


def test_run_service_derives_incident_for_nonzero_exit_code():
    """Verify run_service.ingest_run derives an incident for non-zero exit code even without structured context."""
    db = MagicMock()
    inc_mock = MagicMock()
    inc_mock.incident_id = "inc_fallback_123"

    with patch("app.services.run_service.create_or_get_incident", return_value=inc_mock) as mock_create_inc:
        payload = RunCreate(
            event_id="evt_err_001",
            project_id="proj_001",
            command="javac unknown_failure.java",
            exit_code=1,
            duration_ms=100,
            stderr="Unspecified internal compiler crash\nStack dump...",
            error_context=None,
        )
        resp, is_new = ingest_run(db=db, payload=payload)

        assert mock_create_inc.called
        call_kwargs = mock_create_inc.call_args[1]
        assert call_kwargs["error_type"] == "CommandError"
        assert "Unspecified internal compiler crash" in call_kwargs["error_message"]
        assert resp.incident_id == "inc_fallback_123"


def test_safe_handling_of_malformed_compiler_output():
    """Verify malformed, binary, or noisy output does not crash compiler parser or analyzer."""
    # Completely arbitrary output
    noisy_text = "Some random build log line\n[INFO] Scanning for projects...\n[INFO] --------------------------------"
    diag = parse_compiler_output(noisy_text)
    assert diag.has_diagnostic is False
    assert diag.error_type == "UnrecognizedError"

    # analyze_error_output integration with unknown output
    overall_diag = analyze_error_output(stdout="", stderr=noisy_text)
    assert overall_diag.has_diagnostic is False

    # Empty string
    empty_diag = parse_compiler_output("")
    assert empty_diag.has_diagnostic is False


# ==============================================================================
# 5. CLI Report Rendering for Compiler Errors and Unavailable Notices
# ==============================================================================

def test_cli_rendering_compiler_error_diagnosis():
    """Verify CLI properly renders compiler error diagnosis with Incident ID, Probable Cause, and Steps."""
    diag = BackendDiagnosisResponse(
        status="success",
        event_id="evt_comp_001",
        incident_id="inc_comp_001",
        probable_cause="The Java class declaration contains parentheses after the class name. Java class declarations use braces to delimit the class body, so the compiler expects '{' after Hello.",
        suggested_steps=[
            "Change 'class Hello(){' to 'class Hello {'.",
            "Keep methods and fields inside the class body.",
            "Re-run the Java source file after correcting the declaration.",
        ],
        source="ai_engine/groq-llama-3.3-70b",
    )
    ingestion = IngestionResult(
        success=True,
        is_offline=False,
        incident_id="inc_comp_001",
        diagnosis=diag,
    )

    out = _capture_render(ingestion)
    assert "Incident ID:" in out
    assert "inc_comp_001" in out
    assert "Probable Cause: The Java class declaration contains parentheses" in out
    assert "Suggested Fix:" in out
    assert "- Change 'class Hello(){' to 'class Hello {'." in out
    assert "- Keep methods and fields inside the class body." in out
    assert "- Re-run the Java source file after correcting the declaration." in out


def test_cli_rendering_unavailable_diagnosis_with_incident_id():
    """Verify CLI informs user that diagnosis was unavailable and provides the re-run command."""
    ingestion = IngestionResult(
        success=True,
        is_offline=False,
        incident_id="inc_unavailable_777",
        diagnosis=None,
    )

    out = _capture_render(ingestion)
    assert "Incident ID:" in out
    assert "inc_unavailable_777" in out
    assert "Diagnosis:     Unavailable (Diagnosis request could not be completed)" in out
    assert "devmemory diagnose --incident inc_unavailable_777" in out
