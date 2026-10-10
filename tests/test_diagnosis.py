"""Tests for diagnosis orchestrator in ai_engine.diagnosis."""

import json
import pytest

from ai_engine.diagnosis import diagnose_error
from ai_engine.llm_client import MockLLMClient
from ai_engine.retrieval import AuthorizationContext, InMemoryIncidentRepository
from ai_engine.schemas import (
    DiagnosisRequest,
    DiagnosisResponse,
    FixStatus,
    FixVerificationStatus,
    SourceLocation,
)


def test_diagnose_error_end_to_end_mock():
    """End-to-end diagnosis returns a validated DiagnosisResponse."""
    req = DiagnosisRequest(
        event_id="evt_diag_01",
        project_id="proj_alpha",
        command="python main.py",
        exit_code=1,
        error_message="KeyError: 'session_token'",
        locations=[SourceLocation(file_path="main.py", line=25)],
    )
    auth = AuthorizationContext(user_id="user_1", project_id="proj_alpha")
    mock_client = MockLLMClient()

    resp = diagnose_error(req, auth, llm_client=mock_client)

    assert isinstance(resp, DiagnosisResponse)
    assert resp.event_id == "evt_diag_01"
    assert len(resp.summary) > 0
    assert len(resp.likely_cause) > 0
    assert len(resp.evidence) > 0
    assert len(resp.hypotheses) > 0
    assert len(resp.recommended_steps) > 0
    assert resp.fix_status == FixStatus.UNVERIFIED
    assert resp.confidence is not None


def test_diagnose_error_attaches_retrieved_memory():
    """DiagnosisResponse must include related incidents retrieved from 3-level memory."""
    repo = InMemoryIncidentRepository([
        {
            "incident_id": "inc_past_01",
            "project_id": "proj_alpha",
            "error_message": "KeyError: 'session_token'",
            "command": "python main.py",
            "resolution_summary": "Handled missing session key",
            "verification_status": FixVerificationStatus.VERIFIED,
        }
    ])
    req = DiagnosisRequest(
        event_id="evt_diag_mem",
        project_id="proj_alpha",
        command="python main.py",
        exit_code=1,
        error_message="KeyError: 'session_token'",
    )
    auth = AuthorizationContext(user_id="user_1", project_id="proj_alpha")

    resp = diagnose_error(req, auth, repository=repo, llm_client=MockLLMClient(), threshold=0.50)

    assert len(resp.related_incidents) >= 1
    ids = [inc.incident_id for inc in resp.related_incidents]
    assert "inc_past_01" in ids


def test_diagnose_error_overrides_unwarranted_verified_fix_status():
    """If LLM outputs fix_status='verified', orchestrator must reset it to 'unverified'."""
    custom_json = json.dumps({
        "event_id": "evt_diag_override",
        "summary": "Sample summary",
        "likely_cause": "Sample cause",
        "evidence": ["Exit code 1"],
        "hypotheses": ["Hypothesis A"],
        "recommended_steps": ["Step 1"],
        "uncertainty_description": "None",
        "confidence": 0.9,
        "verification_steps": ["Run test"],
        "fix_status": "verified",  # Falsely claimed as verified by LLM
    })
    req = DiagnosisRequest(
        event_id="evt_diag_override",
        project_id="proj_alpha",
        command="python run.py",
        exit_code=1,
        error_message="TypeError: unsupported operand",
    )
    auth = AuthorizationContext(user_id="user_1", project_id="proj_alpha")
    mock_client = MockLLMClient(custom_response=custom_json)

    resp = diagnose_error(req, auth, llm_client=mock_client)
    assert resp.fix_status == FixStatus.UNVERIFIED


def test_diagnose_error_handles_markdown_code_fences():
    """LLM responses wrapped in ```json ... ``` markdown fences must parse cleanly."""
    fenced_json = """```json
    {
      "event_id": "evt_fenced",
      "summary": "Fenced summary",
      "likely_cause": "Fenced cause",
      "evidence": ["Fenced evidence"],
      "hypotheses": ["Fenced hypothesis"],
      "recommended_steps": ["Fenced step"],
      "uncertainty_description": "None",
      "confidence": 0.85,
      "verification_steps": ["Fenced verify"],
      "fix_status": "unverified"
    }
    ```"""
    req = DiagnosisRequest(
        event_id="evt_fenced",
        project_id="proj_alpha",
        command="pytest",
        exit_code=1,
        error_message="AssertionError",
    )
    auth = AuthorizationContext(user_id="u1", project_id="proj_alpha")
    mock_client = MockLLMClient(custom_response=fenced_json)

    resp = diagnose_error(req, auth, llm_client=mock_client)
    assert resp.summary == "Fenced summary"
    assert resp.event_id == "evt_fenced"


def test_diagnose_error_fallback_on_llm_failure():
    """When LLM provider raises an exception, a fallback DiagnosisResponse is synthesized."""
    class CrashingLLMClient:
        def generate_diagnosis(self, system_prompt: str, user_prompt: str) -> str:
            raise TimeoutError("Groq API request timed out after 30 seconds")

    req = DiagnosisRequest(
        event_id="evt_crash_fallback",
        project_id="proj_alpha",
        command="python script.py",
        exit_code=1,
        error_message="ModuleNotFoundError: No module named 'pydantic'",
    )
    auth = AuthorizationContext(user_id="u1", project_id="proj_alpha")

    # Must NOT raise TimeoutError; must return valid DiagnosisResponse synthesized from KB
    resp = diagnose_error(req, auth, llm_client=CrashingLLMClient(), threshold=0.50)

    assert isinstance(resp, DiagnosisResponse)
    assert resp.event_id == "evt_crash_fallback"
    assert "Fallback diagnosis synthesized" in resp.uncertainty_description
    assert len(resp.recommended_steps) >= 1
    assert resp.fix_status == FixStatus.UNVERIFIED
