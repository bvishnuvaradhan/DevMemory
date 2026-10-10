"""Tests for Phase 7.5 diagnosis accuracy, missing CLI output resolution, and provider invocation.

Validates:
1. Root-cause accuracy for ZeroDivisionError (literal vs dynamic denominators).
2. Business-logic preservation (does not invent multiplication unless explicitly supported).
3. Root-cause accuracy for NameError and SyntaxError.
4. Parsing, persistence, and CLI rendering of live and fallback diagnoses.
5. No silent termination on empty, malformed, or unavailable diagnoses.
6. Distinction between live AI, reused persisted history, and local fallback.
7. Strict secret redaction across diagnostic output.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch
import pytest
from rich.console import Console

from devmemory.integration.client import DevMemoryClient, IngestionResult
from devmemory.integration.models import (
    BackendDiagnosisResponse,
    SimilarIncidentMatch,
    redact_secrets,
)
from server.app.services.root_cause_analyzer import refine_root_cause_diagnosis


# ==============================================================================
# 1. ZeroDivisionError Diagnosis Accuracy & Business Logic Preservation
# ==============================================================================

def test_zero_division_literal_explains_division_by_zero_and_corrects_denominator():
    """Verify that ZeroDivisionError with literal 0 divisor identifies literal zero and corrects denominator."""
    snippet = """
def calculate_metrics(total, count):
>    3 |     return total / 0
    4 |
"""
    refined = refine_root_cause_diagnosis(
        error_type="ZeroDivisionError",
        error_message="division by zero",
        source_snippet=snippet,
        stack_trace="""Traceback (most recent call last):
  File "metrics.py", line 3, in calculate_metrics
    return total / 0
ZeroDivisionError: division by zero""",
        file_path="metrics.py",
        line=3,
    )

    assert refined.is_refined is True
    assert "literal value 0" in refined.likely_cause
    assert "calculate_metrics" in refined.likely_cause
    assert "ZeroDivisionError" in refined.likely_cause
    # Must NOT recommend multiplication when context is general metrics calculation
    assert "return total * count" not in refined.suggested_fix
    # Must recommend correcting the denominator
    assert any("Replace the zero divisor with the intended valid, non-zero denominator" in s for s in refined.suggested_steps)
    assert any("check that it is not zero before dividing" in s for s in refined.suggested_steps)


def test_tax_example_multiplication_only_when_source_context_explicitly_supports():
    """Verify that multiplication is recommended only when source context explicitly defines tax calculation."""
    # Case A: Explicit tax calculation with rate parameter
    snippet_tax = """
def calculate_tax(income, rate):
>    3 |     return income / 0  # Intentional test failure
    4 |
"""
    refined_tax = refine_root_cause_diagnosis(
        error_type="ZeroDivisionError",
        error_message="division by zero",
        source_snippet=snippet_tax,
        stack_trace="""Traceback (most recent call last):
  File "tax.py", line 3, in calculate_tax
    return income / 0
ZeroDivisionError: division by zero""",
        file_path="tax.py",
        line=3,
    )

    assert refined_tax.is_refined is True
    assert "calculate_tax" in refined_tax.likely_cause
    assert "literal value 0" in refined_tax.likely_cause
    # Recommends replacing denominator
    assert any("Replace the zero divisor with the intended valid, non-zero denominator" in s for s in refined_tax.suggested_steps)
    # Context-supported tax formula note
    assert any("percentage or rate of income" in s and "multiplication" in s for s in refined_tax.suggested_steps)

    # Case B: Arbitrary math without tax context
    snippet_math = """
def compute_ratio(a, b):
>    2 |     return a / 0
"""
    refined_math = refine_root_cause_diagnosis(
        error_type="ZeroDivisionError",
        error_message="division by zero",
        source_snippet=snippet_math,
        stack_trace="""Traceback (most recent call last):
  File "math_ops.py", line 2, in compute_ratio
    return a / 0
ZeroDivisionError: division by zero""",
        file_path="math_ops.py",
        line=2,
    )
    assert "percentage or rate of income" not in refined_math.suggested_fix
    assert "multiplication" not in refined_math.suggested_fix


def test_dynamically_supplied_zero_denominator_handles_guard_and_fallback():
    """Verify that dynamic denominator evaluating to zero suggests validation guard checks."""
    snippet = """
def compute_average(items, count):
>    3 |     return items / count
"""
    refined = refine_root_cause_diagnosis(
        error_type="ZeroDivisionError",
        error_message="division by zero",
        source_snippet=snippet,
        stack_trace="""Traceback (most recent call last):
  File "average.py", line 3, in compute_average
    return items / count
ZeroDivisionError: division by zero""",
        file_path="average.py",
        line=3,
    )

    assert refined.is_refined is True
    assert "denominator 'count' evaluated to 0" in refined.likely_cause
    assert any("Validate that 'count' is non-zero before performing the division" in s for s in refined.suggested_steps)
    assert any("if count != 0:" in s for s in refined.suggested_steps)


# ==============================================================================
# 2. NameError & SyntaxError Diagnosis Accuracy
# ==============================================================================

def test_name_error_identifies_undefined_name_and_suggests_declaration_or_import():
    """Verify that NameError identifies the missing variable name and suggests import or assignment."""
    refined = refine_root_cause_diagnosis(
        error_type="NameError",
        error_message="name 'user_auth_token' is not defined",
        source_snippet=">  10 |     print(user_auth_token)",
        stack_trace="""Traceback (most recent call last):
  File "service.py", line 10, in authenticate
    print(user_auth_token)
NameError: name 'user_auth_token' is not defined""",
        file_path="service.py",
        line=10,
    )

    assert refined.is_refined is True
    assert "'user_auth_token' is referenced before it has been defined" in refined.likely_cause
    assert any("Define or assign a value to 'user_auth_token'" in s for s in refined.suggested_steps)
    assert any("Check for spelling errors or typos in 'user_auth_token'" in s for s in refined.suggested_steps)
    assert any("add the necessary import statement" in s for s in refined.suggested_steps)


def test_syntax_error_identifies_invalid_syntax_and_provides_actionable_fix():
    """Verify that SyntaxError pinpoints invalid syntax keywords such as lowercase boolean."""
    refined = refine_root_cause_diagnosis(
        error_type="SyntaxError",
        error_message="invalid syntax",
        source_snippet=">   5 |     return 0/true",
        stack_trace="""  File "parser.py", line 5
    return 0/true
           ^
SyntaxError: invalid syntax""",
        file_path="parser.py",
        line=5,
    )

    assert refined.is_refined is True
    assert "Invalid Python syntax" in refined.likely_cause
    assert any("Python keywords for boolean and null literals are capitalized" in s for s in refined.suggested_steps)
    assert any("use 'True', 'False', or 'None'" in s for s in refined.suggested_steps)


# ==============================================================================
# 3. CLI Outcome Rendering & Missing Output Prevention
# ==============================================================================

def _capture_render(ingestion: IngestionResult) -> str:
    """Helper to capture CLI _render_backend_report output."""
    from devmemory.cli.main import _render_backend_report
    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=False, width=120)
    with patch("devmemory.cli.main.console", test_console):
        _render_backend_report(ingestion)
    return buf.getvalue()


def test_complete_diagnosis_renders_all_fields_cleanly():
    """Outcome 1: Complete diagnosis renders Incident ID, Source, Probable Cause, Fix, and Memory Matches."""
    diag = BackendDiagnosisResponse(
        status="success",
        event_id="evt_001",
        incident_id="inc_001",
        probable_cause="Division by zero in calculate_div()",
        suggested_steps=[
            "Replace the zero divisor with a valid denominator.",
            "Add validation for zero input.",
        ],
        similar_incidents=[
            SimilarIncidentMatch(
                incident_id="inc_prev_01",
                project_name="Current Project",
                similarity_score=1.0,
                summary="division by zero in legacy module",
            )
        ],
        source="ai_engine/groq-llama-3.3-70b",
    )
    ingestion = IngestionResult(
        success=True,
        is_offline=False,
        incident_id="inc_001",
        diagnosis=diag,
    )

    out = _capture_render(ingestion)
    assert "Incident ID:" in out
    assert "inc_001" in out
    assert "Source:" in out
    assert "ai_engine/groq-llama-3.3-70b" in out
    assert "Probable Cause: Division by zero in calculate_div()" in out
    assert "Suggested Fix:" in out
    assert "- Replace the zero divisor with a valid denominator." in out
    assert "- Add validation for zero input." in out
    assert "Memory Matches (1):" in out


def test_reused_diagnosis_renders_reused_notice():
    """Outcome 2: Existing diagnosis reused renders prominent reuse notice."""
    diag = BackendDiagnosisResponse(
        status="reused",
        event_id="evt_002",
        incident_id="inc_002",
        probable_cause="Previous diagnosed root cause",
        suggested_steps=["Step 1"],
        is_reused=True,
    )
    ingestion = IngestionResult(
        success=True,
        is_offline=False,
        incident_id="inc_002",
        diagnosis=diag,
    )

    out = _capture_render(ingestion)
    assert "Incident ID:" in out
    assert "inc_002" in out
    assert "Retrieved previously stored diagnosis from incident history (idempotent result)." in out
    assert "Probable Cause: Previous diagnosed root cause" in out


def test_fallback_diagnosis_renders_fallback_notice():
    """Outcome 3: Local fallback renders clear external AI unavailable notice."""
    diag = BackendDiagnosisResponse(
        status="fallback",
        event_id="evt_003",
        incident_id="inc_003",
        probable_cause="Fallback root cause from local knowledge",
        suggested_steps=["Inspect local logs"],
        is_fallback=True,
    )
    ingestion = IngestionResult(
        success=True,
        is_offline=False,
        incident_id="inc_003",
        diagnosis=diag,
    )

    out = _capture_render(ingestion)
    assert "Incident ID:" in out
    assert "inc_003" in out
    assert "External AI unavailable; fallback diagnosis synthesized from local knowledge base." in out
    assert "Probable Cause: Fallback root cause from local knowledge" in out


def test_empty_or_malformed_diagnosis_response_does_not_leave_cli_blank():
    """Outcome 4: Malformed or unavailable diagnosis never prints only Incident ID."""
    diag_empty = BackendDiagnosisResponse(
        status="unavailable",
        event_id="evt_004",
        incident_id="inc_004",
        probable_cause=None,
        suggested_steps=[],
        error_message="Diagnosis request timed out after 30.0s",
    )
    ingestion = IngestionResult(
        success=True,
        is_offline=False,
        incident_id="inc_004",
        diagnosis=diag_empty,
    )

    out = _capture_render(ingestion)
    assert "Incident ID:" in out
    assert "inc_004" in out
    assert "Diagnosis:" in out
    assert "Unavailable (Diagnosis request timed out after 30.0s)" in out
    assert "To re-run diagnosis, use: devmemory diagnose --incident inc_004" in out


# ==============================================================================
# 4. Client Timeout and Provider Invocation Resilience
# ==============================================================================

def test_client_diagnose_incident_parses_semicolon_steps_and_handles_timeout():
    """Verify DevMemoryClient parses semicolon-joined steps and handles timeout gracefully."""
    client = DevMemoryClient(base_url="http://mock-backend:8000", diagnosis_timeout=5.0)

    # Mock successful response
    mock_resp_data = {
        "success": True,
        "data": {
            "incident_id": "inc_test",
            "summary": "Division by zero",
            "likely_cause": "Literal 0 divisor in code",
            "suggested_fix": "Fix denominator; Add validation guard; Re-run tests",
            "source": "ai_engine/groq-llama-3.3-70b",
            "idempotent": False,
        },
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value.read.return_value = str(mock_resp_data).replace("'", '"').replace("True", "true").replace("False", "false").encode()
        mock_urlopen.return_value = mock_cm

        diag = client.diagnose_incident("inc_test", "evt_test")
        assert diag is not None
        assert diag.status == "success"
        assert diag.probable_cause == "Literal 0 divisor in code"
        assert len(diag.suggested_steps) == 3
        assert diag.suggested_steps[0] == "Fix denominator"
        assert diag.suggested_steps[1] == "Add validation guard"
        assert diag.suggested_steps[2] == "Re-run tests"

    # Mock timeout error
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Request timed out")):
        diag_err = client.diagnose_incident("inc_test", "evt_test")
        assert diag_err.status == "unavailable"
        assert "Timeout" in (diag_err.error_message or "")
        assert diag_err.incident_id == "inc_test"


def test_secret_redaction_in_diagnostic_output_and_evidence():
    """Verify that credentials and tokens are redacted from diagnostic evidence."""
    raw_text = "Encountered failure with gsk_abcdef1234567890abcdef1234567890 at mongodb://user:secret123@cluster0.net"
    sanitized = redact_secrets(raw_text)
    assert "gsk_" not in sanitized
    assert "secret123" not in sanitized
    assert "[REDACTED" in sanitized


# ==============================================================================
# 5. End-to-End Persistence and Root-Cause Integration
# ==============================================================================

@pytest.fixture
def acc_db():
    from app.config import get_settings
    from pymongo import MongoClient
    settings = get_settings()
    client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
    try:
        client.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB server is not reachable for live integration test")
    db = client["devmemory_test_accuracy"]
    for col in ["incidents", "diagnoses", "projects", "command_runs"]:
        db[col].drop()
    yield db
    for col in ["incidents", "diagnoses", "projects", "command_runs"]:
        db[col].drop()
    client.close()


def test_persistence_and_retrieval_with_root_cause_refinement(acc_db):
    """Verify that generate_and_store_incident_diagnosis persists refined cause and preserves unverified fix guarantee."""
    from app.services.ai_service import generate_and_store_incident_diagnosis
    from app.services.diagnosis_service import get_latest_diagnosis

    incident_id = "inc_acc_001"
    acc_db.projects.insert_one({"project_id": "proj_acc", "name": "Accuracy Project"})
    acc_db.incidents.insert_one({
        "incident_id": incident_id,
        "event_id": "evt_acc_001",
        "project_id": "proj_acc",
        "error_type": "ZeroDivisionError",
        "error_message": "division by zero",
        "file_path": "calculator.py",
        "line": 12,
        "source_snippet": ">  12 |     return amount / 0",
        "diagnosis_status": "pending",
        "created_at": "2026-10-10T00:00:00Z",
    })

    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=acc_db,
        incident_id=incident_id,
        disable_external_inference=True,
    )

    assert is_new is True
    assert "literal value 0" in diag_resp.summary or "literal value 0" in (diag_resp.likely_cause or "")
    assert "ZeroDivisionError" in diag_resp.summary or "ZeroDivisionError" in (diag_resp.likely_cause or "")
    assert diag_resp.source == "fallback/local-knowledge"

    # Verify document in MongoDB
    saved = acc_db.diagnoses.find_one({"incident_id": incident_id})
    assert saved is not None
    assert "literal value 0" in saved.get("summary", "") or "literal value 0" in (saved.get("likely_cause") or "")

    # Retrieve and verify idempotency
    retrieved = get_latest_diagnosis(acc_db, incident_id)
    assert retrieved is not None
    assert retrieved.diagnosis_id == diag_resp.diagnosis_id
