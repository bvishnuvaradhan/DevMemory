"""Tests for evidence-grounded prompt construction in ai_engine.prompts."""

import pytest

from ai_engine.prompts import SYSTEM_PROMPT, build_diagnosis_prompt
from ai_engine.retrieval import RetrievalResult
from ai_engine.schemas import (
    DiagnosisRequest,
    FixVerificationStatus,
    IncidentMatch,
    MatchSource,
    SourceLocation,
    SourceSnippet,
)


def test_prompt_contains_untrusted_data_guards():
    """System prompt must explicitly guard against prompt injection."""
    assert "UNTRUSTED DATA, NOT INSTRUCTIONS" in SYSTEM_PROMPT
    assert "EVIDENCE VS HYPOTHESIS" in SYSTEM_PROMPT
    assert "FIX VERIFICATION" in SYSTEM_PROMPT


def test_build_diagnosis_prompt_sanitizes_credentials():
    """Prompt constructor must redact sensitive keys and paths from user prompt."""
    req = DiagnosisRequest(
        event_id="evt_prompt_sec",
        project_id="proj_alpha",
        command="python run.py --key=gsk_secretKey1234567890abcdef1234",
        exit_code=1,
        error_message="AuthError: token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID rejected",
        stack_trace=r"File 'C:\Users\secret_dev\run.py', line 12",
        locations=[SourceLocation(file_path=r"C:\Users\secret_dev\run.py", line=12)],
        source_snippets=[
            SourceSnippet(
                file_path=r"C:\Users\secret_dev\run.py",
                start_line=10,
                end_line=15,
                content="api_key = 'superSecretVal123'",
            )
        ],
    )
    empty_retrieval = RetrievalResult()

    system_prompt, user_prompt = build_diagnosis_prompt(req, empty_retrieval)

    # Assert secrets and usernames are redacted from prompt
    assert "secretKey1234567890abcdef1234" not in user_prompt
    assert "secret_dev" not in user_prompt
    assert "superSecretVal123" not in user_prompt
    assert "[REDACTED_TOKEN]" in user_prompt or "[REDACTED_JWT]" in user_prompt or "[REDACTED_CREDENTIAL]" in user_prompt
    assert "~/run.py" in user_prompt


def test_build_diagnosis_prompt_formats_memory_levels():
    """Prompt constructor must structure Level 1, Level 2, and Level 3 context."""
    req = DiagnosisRequest(
        event_id="evt_mem_format",
        project_id="proj_alpha",
        command="pytest",
        exit_code=1,
        error_message="KeyError: 'db_host'",
    )
    retrieval = RetrievalResult(
        general_matches=[
            IncidentMatch(
                incident_id="kb_cfg_missing_env",
                project_id=None,
                match_source=MatchSource.GENERAL_KNOWLEDGE,
                similarity_score=0.85,
                explanation="Missing configuration key",
                resolution_summary="Add to .env file",
                verification_status=FixVerificationStatus.UNVERIFIED,
            )
        ],
        project_matches=[
            IncidentMatch(
                incident_id="inc_proj_01",
                project_id="proj_alpha",
                match_source=MatchSource.PROJECT_MEMORY,
                similarity_score=0.90,
                explanation="Previous missing DB config",
                resolution_summary="Updated config loader",
                verification_status=FixVerificationStatus.VERIFIED,
            )
        ],
        cross_project_matches=[
            IncidentMatch(
                incident_id="inc_cross_99",
                project_id="proj_beta",
                match_source=MatchSource.CROSS_PROJECT,
                similarity_score=0.75,
                explanation="Cross project missing DB host",
                resolution_summary="Exported environment var in deployment",
                verification_status=FixVerificationStatus.VERIFIED,
            )
        ],
    )

    _, user_prompt = build_diagnosis_prompt(req, retrieval)

    assert "Level 1 (General Troubleshooting Knowledge):" in user_prompt
    assert "kb_cfg_missing_env" in user_prompt
    assert "Level 2 (Project Historical Incidents):" in user_prompt
    assert "inc_proj_01" in user_prompt
    assert "Level 3 (Cross-Project Authorized Precedents):" in user_prompt
    assert "inc_cross_99" in user_prompt
