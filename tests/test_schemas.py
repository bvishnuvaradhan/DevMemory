"""Tests for ai_engine.schemas Pydantic models.

Validates:
1. Valid DiagnosisRequest instantiation.
2. Valid DiagnosisResponse instantiation.
3. Missing required identifiers.
4. Invalid line and column numbers.
5. Out-of-bounds similarity and confidence scores.
6. Invalid enum values.
7. Snippet end line earlier than start line.
8. JSON serialization and round-trip parsing.
9. Defaults for optional collections.
10. Explicit verification status behavior.
"""

import pytest
from pydantic import ValidationError

from ai_engine.schemas import (
    DiagnosisRequest,
    DiagnosisResponse,
    FixOutcome,
    FixStatus,
    FixVerificationStatus,
    IncidentMatch,
    KnowledgeBaseItem,
    MatchSource,
    SourceLocation,
    SourceSnippet,
)


def test_1_valid_diagnosis_request():
    """Test valid instantiation of DiagnosisRequest."""
    req = DiagnosisRequest(
        event_id="evt_test_001",
        project_id="proj_backend",
        command="pytest tests/test_api.py",
        exit_code=1,
        error_message="KeyError: 'authorization'",
        stack_trace="File 'api/auth.py', line 45, in get_token\n  return headers['authorization']",
        locations=[
            SourceLocation(file_path="api/auth.py", line=45, column=10, function_name="get_token")
        ],
        source_snippets=[
            SourceSnippet(
                file_path="api/auth.py",
                start_line=40,
                end_line=50,
                content="def get_token(headers):\n    return headers['authorization']",
            )
        ],
        allow_cross_project=True,
    )

    assert req.event_id == "evt_test_001"
    assert req.project_id == "proj_backend"
    assert req.exit_code == 1
    assert len(req.locations) == 1
    assert req.locations[0].line == 45
    assert len(req.source_snippets) == 1
    assert req.allow_cross_project is True


def test_2_valid_diagnosis_response():
    """Test valid instantiation of DiagnosisResponse."""
    resp = DiagnosisResponse(
        event_id="evt_test_001",
        summary="Missing 'authorization' header in incoming HTTP request.",
        likely_cause="The authorization header dictionary lookup was performed without checking existence or using .get().",
        evidence=[
            "KeyError: 'authorization' at api/auth.py:45",
            "Exit code 1 returned by pytest",
        ],
        hypotheses=[
            "Client request omitted Authorization header",
            "Header casing mismatch (e.g. 'Authorization' vs 'authorization')",
        ],
        recommended_steps=[
            "Use headers.get('authorization') instead of direct indexing",
            "Implement CaseInsensitiveDict or lowercased lookup",
        ],
        related_incidents=[
            IncidentMatch(
                incident_id="inc_kb_401",
                project_id=None,
                match_source=MatchSource.GENERAL_KNOWLEDGE,
                similarity_score=0.92,
                explanation="Standard Python dictionary key access without default",
                resolution_summary="Replace direct subscript with .get()",
                verification_status=FixVerificationStatus.UNVERIFIED,
            )
        ],
        uncertainty_description="Cannot confirm whether headers are pre-normalized by middleware without inspecting server configuration.",
        confidence=0.88,
        verification_steps=[
            "Re-run pytest tests/test_api.py",
            "Send an HTTP request with and without the header",
        ],
        fix_status=FixStatus.UNVERIFIED,
    )

    assert resp.event_id == "evt_test_001"
    assert resp.confidence == 0.88
    assert resp.fix_status == FixStatus.UNVERIFIED
    assert len(resp.related_incidents) == 1
    assert resp.related_incidents[0].verification_status == FixVerificationStatus.UNVERIFIED


def test_3_missing_required_identifiers():
    """Test that missing or empty required identifiers raise ValidationError."""
    # Missing event_id
    with pytest.raises(ValidationError) as exc_info:
        DiagnosisRequest(
            project_id="proj_1",
            command="python main.py",
            exit_code=1,
            error_message="SyntaxError",
        )
    errors = str(exc_info.value)
    assert "event_id" in errors

    # Empty string for event_id
    with pytest.raises(ValidationError):
        DiagnosisRequest(
            event_id="",
            project_id="proj_1",
            command="python main.py",
            exit_code=1,
            error_message="SyntaxError",
        )

    # Empty string for project_id
    with pytest.raises(ValidationError):
        DiagnosisRequest(
            event_id="evt_1",
            project_id="",
            command="python main.py",
            exit_code=1,
            error_message="SyntaxError",
        )


def test_4_invalid_line_and_column_numbers():
    """Test that line and column numbers must be positive."""
    # line = 0 is invalid
    with pytest.raises(ValidationError):
        SourceLocation(file_path="main.py", line=0)

    # line = -1 is invalid
    with pytest.raises(ValidationError):
        SourceLocation(file_path="main.py", line=-1)

    # column = 0 is invalid
    with pytest.raises(ValidationError):
        SourceLocation(file_path="main.py", line=10, column=0)

    # column = -5 is invalid
    with pytest.raises(ValidationError):
        SourceLocation(file_path="main.py", line=10, column=-5)


def test_5_invalid_similarity_and_confidence_scores():
    """Test that similarity and confidence must be bounded between 0.0 and 1.0."""
    # similarity_score > 1.0
    with pytest.raises(ValidationError):
        IncidentMatch(
            incident_id="inc_1",
            match_source=MatchSource.PROJECT_MEMORY,
            similarity_score=1.05,
            explanation="Test explanation",
        )

    # similarity_score < 0.0
    with pytest.raises(ValidationError):
        IncidentMatch(
            incident_id="inc_1",
            match_source=MatchSource.PROJECT_MEMORY,
            similarity_score=-0.1,
            explanation="Test explanation",
        )

    # confidence > 1.0
    with pytest.raises(ValidationError):
        DiagnosisResponse(
            event_id="evt_1",
            summary="Sum",
            likely_cause="Cause",
            uncertainty_description="Uncertainty",
            confidence=1.5,
        )

    # confidence < 0.0
    with pytest.raises(ValidationError):
        DiagnosisResponse(
            event_id="evt_1",
            summary="Sum",
            likely_cause="Cause",
            uncertainty_description="Uncertainty",
            confidence=-0.01,
        )


def test_6_invalid_enum_values():
    """Test that unknown enum strings are rejected."""
    with pytest.raises(ValidationError):
        IncidentMatch(
            incident_id="inc_1",
            match_source="invalid_source",  # Not a valid MatchSource
            similarity_score=0.5,
            explanation="Explanation",
        )

    with pytest.raises(ValidationError):
        IncidentMatch(
            incident_id="inc_1",
            match_source=MatchSource.PROJECT_MEMORY,
            similarity_score=0.5,
            explanation="Explanation",
            verification_status="guaranteed_resolved",  # Not a valid FixVerificationStatus
        )

    with pytest.raises(ValidationError):
        DiagnosisResponse(
            event_id="evt_1",
            summary="Sum",
            likely_cause="Cause",
            uncertainty_description="Uncertainty",
            fix_status="auto_fixed",  # Not a valid FixStatus
        )


def test_7_snippet_end_line_earlier_than_start_line():
    """Test that snippet rejects end_line < start_line."""
    # end_line < start_line should fail
    with pytest.raises(ValidationError) as exc_info:
        SourceSnippet(
            file_path="app.py",
            start_line=50,
            end_line=40,
            content="print('hello')",
        )
    assert "end_line" in str(exc_info.value)

    # Equal start_line and end_line is valid (single-line snippet)
    snippet = SourceSnippet(
        file_path="app.py",
        start_line=50,
        end_line=50,
        content="print('hello')",
    )
    assert snippet.start_line == snippet.end_line


def test_8_json_serialization_round_trip():
    """Test JSON serialization and deserialization integrity."""
    orig_req = DiagnosisRequest(
        event_id="evt_round_trip",
        project_id="proj_xyz",
        command="node index.js",
        exit_code=1,
        error_message="TypeError: undefined is not a function",
        locations=[SourceLocation(file_path="index.js", line=12, column=5)],
        source_snippets=[
            SourceSnippet(file_path="index.js", start_line=10, end_line=15, content="const x = 1;")
        ],
    )

    json_str = orig_req.model_dump_json()
    reloaded = DiagnosisRequest.model_validate_json(json_str)

    assert reloaded == orig_req
    assert reloaded.event_id == "evt_round_trip"
    assert reloaded.locations[0].line == 12


def test_9_defaults_for_optional_collections():
    """Test that optional collections default to empty lists and None values."""
    req = DiagnosisRequest(
        event_id="evt_minimal",
        project_id="proj_minimal",
        command="cargo run",
        exit_code=101,
        error_message="panic: index out of bounds",
    )

    assert req.stack_trace is None
    assert req.locations == []
    assert req.source_snippets == []
    assert req.allow_cross_project is False

    resp = DiagnosisResponse(
        event_id="evt_minimal",
        summary="Panic due to index out of bounds",
        likely_cause="Vector was indexed beyond its length",
        uncertainty_description="Exact length at runtime unknown",
    )

    assert resp.evidence == []
    assert resp.hypotheses == []
    assert resp.recommended_steps == []
    assert resp.related_incidents == []
    assert resp.confidence is None
    assert resp.verification_steps == []
    assert resp.fix_status == FixStatus.UNVERIFIED


def test_10_explicit_verification_status():
    """Ensure verification status is explicit and never inferred as VERIFIED by default."""
    match = IncidentMatch(
        incident_id="inc_007",
        match_source=MatchSource.CROSS_PROJECT,
        similarity_score=0.75,
        explanation="Similar error pattern observed",
    )
    # Default must be UNVERIFIED
    assert match.verification_status == FixVerificationStatus.UNVERIFIED

    # Explicit verified status is accepted only when passed
    verified_match = IncidentMatch(
        incident_id="inc_008",
        match_source=MatchSource.PROJECT_MEMORY,
        similarity_score=0.85,
        explanation="Previously verified fix",
        resolution_summary="Updated config.json",
        verification_status=FixVerificationStatus.VERIFIED,
    )
    assert verified_match.verification_status == FixVerificationStatus.VERIFIED

    # Check FixOutcome recording
    outcome = FixOutcome(
        outcome_id="out_123",
        incident_id="inc_008",
        project_id="proj_xyz",
        verification_status=FixVerificationStatus.VERIFIED,
        verification_command="pytest",
        recurred=False,
    )
    assert outcome.verification_status == FixVerificationStatus.VERIFIED
    assert outcome.recurred is False
