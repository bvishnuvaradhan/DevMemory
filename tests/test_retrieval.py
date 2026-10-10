"""Tests for three-level memory retrieval architecture in ai_engine.retrieval."""

import pytest

from ai_engine.matching import compute_error_signature
from ai_engine.retrieval import (
    AuthorizationContext,
    InMemoryIncidentRepository,
    retrieve_memory,
)
from ai_engine.schemas import (
    DiagnosisRequest,
    FixVerificationStatus,
    MatchSource,
    SourceLocation,
    SourceSnippet,
)


@pytest.fixture
def auth_authorized_cross():
    return AuthorizationContext(
        user_id="user_admin",
        project_id="proj_alpha",
        has_project_access=True,
        has_cross_project_read=True,
    )


@pytest.fixture
def auth_restricted():
    return AuthorizationContext(
        user_id="user_dev",
        project_id="proj_alpha",
        has_project_access=True,
        has_cross_project_read=False,
    )


def test_level_1_general_knowledge_match():
    """Level 1 finds relevant curated knowledge base entries offline."""
    req = DiagnosisRequest(
        event_id="evt_l1",
        project_id="proj_alpha",
        command="python app.py",
        exit_code=1,
        error_message="ModuleNotFoundError: No module named 'pydantic'",
        allow_cross_project=False,
    )
    auth = AuthorizationContext(user_id="u1", project_id="proj_alpha")

    result = retrieve_memory(req, auth, threshold=0.60)
    assert len(result.general_matches) >= 1
    best_match = result.general_matches[0]
    assert best_match.incident_id == "kb_py_mod_not_found"
    assert best_match.match_source == MatchSource.GENERAL_KNOWLEDGE
    assert best_match.project_id is None
    assert best_match.verification_status == FixVerificationStatus.UNVERIFIED


def test_level_1_no_irrelevant_matches():
    """Unrelated errors should yield no matches above standard threshold."""
    req = DiagnosisRequest(
        event_id="evt_unrelated",
        project_id="proj_alpha",
        command="custom_tool do_something",
        exit_code=42,
        error_message="CustomBizarreExitCondition: Code 998244353",
    )
    auth = AuthorizationContext(user_id="u1", project_id="proj_alpha")

    result = retrieve_memory(req, auth, threshold=0.75)
    assert len(result.general_matches) == 0


def test_level_2_current_project_memory_retrieval():
    """Level 2 retrieves historical incidents belonging to current project."""
    repo = InMemoryIncidentRepository([
        {
            "incident_id": "inc_proj_001",
            "project_id": "proj_alpha",
            "error_message": "KeyError: 'database_url'",
            "command": "pytest tests/",
            "resolution_summary": "Added fallback in config.py: os.getenv('DATABASE_URL', 'sqlite:///')",
            "verification_status": FixVerificationStatus.VERIFIED,
        },
        {
            "incident_id": "inc_proj_other",
            "project_id": "proj_beta",
            "error_message": "KeyError: 'database_url'",
            "command": "pytest tests/",
            "resolution_summary": "Exported variable in CI",
            "verification_status": FixVerificationStatus.VERIFIED,
        },
    ])

    req = DiagnosisRequest(
        event_id="evt_l2",
        project_id="proj_alpha",
        command="pytest tests/",
        exit_code=1,
        error_message="KeyError: 'database_url'",
    )
    auth = AuthorizationContext(user_id="u1", project_id="proj_alpha", has_cross_project_read=False)

    result = retrieve_memory(req, auth, repository=repo, threshold=0.50)
    assert len(result.project_matches) == 1
    match = result.project_matches[0]
    assert match.incident_id == "inc_proj_001"
    assert match.project_id == "proj_alpha"
    assert match.match_source == MatchSource.PROJECT_MEMORY
    assert match.verification_status == FixVerificationStatus.VERIFIED


def test_level_2_prevents_leak_of_other_projects():
    """Project-memory level must never return incidents from another project."""
    repo = InMemoryIncidentRepository([
        {
            "incident_id": "inc_secret_proj",
            "project_id": "proj_classified",
            "error_message": "TypeError: Cannot read properties of undefined (reading 'map')",
            "command": "npm test",
            "resolution_summary": "Fixed nested prop",
            "verification_status": FixVerificationStatus.VERIFIED,
        }
    ])

    req = DiagnosisRequest(
        event_id="evt_leak_check",
        project_id="proj_alpha",
        command="npm test",
        exit_code=1,
        error_message="TypeError: Cannot read properties of undefined (reading 'map')",
    )
    auth = AuthorizationContext(user_id="u1", project_id="proj_alpha", has_cross_project_read=False)

    result = retrieve_memory(req, auth, repository=repo, threshold=0.50)
    # Project matches must be strictly for proj_alpha
    assert len(result.project_matches) == 0


def test_level_3_denies_cross_project_when_authorization_absent(auth_restricted):
    """Cross-project matches must be empty if auth_context.has_cross_project_read is False."""
    repo = InMemoryIncidentRepository([
        {
            "incident_id": "inc_cross_1",
            "project_id": "proj_beta",
            "error_message": "TypeError: Cannot read properties of undefined (reading 'map')",
            "command": "npm test",
            "resolution_summary": "Added optional chaining",
            "is_public": True,
            "verification_status": FixVerificationStatus.VERIFIED,
        }
    ])

    req = DiagnosisRequest(
        event_id="evt_cross_denied",
        project_id="proj_alpha",
        command="npm test",
        exit_code=1,
        error_message="TypeError: Cannot read properties of undefined (reading 'map')",
        allow_cross_project=True,  # Client wants it, but server auth lacks grant!
    )

    result = retrieve_memory(req, auth_restricted, repository=repo, threshold=0.50)
    assert len(result.cross_project_matches) == 0


def test_level_3_allows_cross_project_when_authorized(auth_authorized_cross):
    """Cross-project matches allowed when server authorized, project is public, and user opted in."""
    repo = InMemoryIncidentRepository([
        {
            "incident_id": "inc_cross_ok",
            "project_id": "proj_beta",
            "error_message": "TypeError: Cannot read properties of undefined (reading 'map')",
            "command": "npm test",
            "resolution_summary": "Added optional chaining ?.map()",
            "is_public": True,
            "disclose_project_id": True,
            "verification_status": FixVerificationStatus.VERIFIED,
        },
        {
            "incident_id": "inc_cross_private",
            "project_id": "proj_gamma",
            "error_message": "TypeError: Cannot read properties of undefined (reading 'map')",
            "command": "npm test",
            "resolution_summary": "Private proprietary fix",
            "is_public": False,  # Candidate is private
            "verification_status": FixVerificationStatus.VERIFIED,
        },
    ])

    req = DiagnosisRequest(
        event_id="evt_cross_ok",
        project_id="proj_alpha",
        command="npm test",
        exit_code=1,
        error_message="TypeError: Cannot read properties of undefined (reading 'map')",
        allow_cross_project=True,
    )

    result = retrieve_memory(req, auth_authorized_cross, repository=repo, threshold=0.50)
    assert len(result.cross_project_matches) == 1
    match = result.cross_project_matches[0]
    assert match.incident_id == "inc_cross_ok"
    assert match.match_source == MatchSource.CROSS_PROJECT
    assert match.project_id == "proj_beta"
    assert match.verification_status == FixVerificationStatus.VERIFIED


def test_level_3_omits_private_snippets_and_redacts_secrets(auth_authorized_cross):
    """Cross-project output must redact embedded credentials and paths."""
    repo = InMemoryIncidentRepository([
        {
            "incident_id": "inc_leak_check",
            "project_id": "proj_beta",
            "error_message": "AuthError: failed",
            "command": "python run.py",
            "resolution_summary": "Set api_key='gsk_fakeKey1234567890abcdef12345' in C:\\Users\\secret_admin\\cfg.py",
            "is_public": True,
            "verification_status": FixVerificationStatus.VERIFIED,
        }
    ])

    req = DiagnosisRequest(
        event_id="evt_redact_check",
        project_id="proj_alpha",
        command="python run.py",
        exit_code=1,
        error_message="AuthError: failed",
        allow_cross_project=True,
    )

    result = retrieve_memory(req, auth_authorized_cross, repository=repo, threshold=0.40)
    assert len(result.cross_project_matches) == 1
    match = result.cross_project_matches[0]
    assert "gsk_fakeKey1234567890abcdef12345" not in match.resolution_summary
    assert "secret_admin" not in match.resolution_summary
    assert "[REDACTED" in match.resolution_summary


def test_preserves_explicit_fix_status():
    """Unverified status in candidate must remain UNVERIFIED; VERIFIED must remain VERIFIED."""
    repo = InMemoryIncidentRepository([
        {
            "incident_id": "inc_unverified",
            "project_id": "proj_alpha",
            "error_message": "ValueError: invalid parameter",
            "command": "pytest",
            "verification_status": FixVerificationStatus.UNVERIFIED,
        },
        {
            "incident_id": "inc_failed",
            "project_id": "proj_alpha",
            "error_message": "ValueError: invalid parameter",
            "command": "pytest",
            "verification_status": FixVerificationStatus.FAILED,
        },
    ])

    req = DiagnosisRequest(
        event_id="evt_status_check",
        project_id="proj_alpha",
        command="pytest",
        exit_code=1,
        error_message="ValueError: invalid parameter",
    )
    auth = AuthorizationContext(user_id="u1", project_id="proj_alpha")

    result = retrieve_memory(req, auth, repository=repo, threshold=0.50)
    statuses = {m.incident_id: m.verification_status for m in result.project_matches}
    assert statuses["inc_unverified"] == FixVerificationStatus.UNVERIFIED
    assert statuses["inc_failed"] == FixVerificationStatus.FAILED


def test_ranking_exact_signature_ahead_of_weaker_candidates():
    """Exact signature matches get prioritized ahead of generic keyword matches."""
    err_msg = "KeyError: 'auth_token'"
    stack = "File 'auth.py', line 10, in verify\n  return d['auth_token']"
    exact_sig = compute_error_signature(err_msg, stack, "python test.py")

    repo = InMemoryIncidentRepository([
        {
            "incident_id": "inc_partial",
            "project_id": "proj_alpha",
            "error_message": "KeyError: 'other_token'",
            "command": "python test.py",
        },
        {
            "incident_id": "inc_exact",
            "project_id": "proj_alpha",
            "error_message": err_msg,
            "stack_trace": stack,
            "command": "python test.py",
            "error_signature": exact_sig,
        },
    ])

    req = DiagnosisRequest(
        event_id="evt_rank",
        project_id="proj_alpha",
        command="python test.py",
        exit_code=1,
        error_message=err_msg,
        stack_trace=stack,
    )
    auth = AuthorizationContext(user_id="u1", project_id="proj_alpha")

    result = retrieve_memory(req, auth, repository=repo, threshold=0.40)
    assert len(result.project_matches) >= 2
    assert result.project_matches[0].incident_id == "inc_exact"
    assert result.project_matches[0].similarity_score > result.project_matches[1].similarity_score


def test_configurable_threshold():
    """Higher threshold filters out moderate matches; lower threshold includes them."""
    repo = InMemoryIncidentRepository([
        {
            "incident_id": "inc_moderate",
            "project_id": "proj_alpha",
            "error_message": "KeyError: 'timeout_value'",
            "command": "pytest",
        }
    ])

    req = DiagnosisRequest(
        event_id="evt_thresh",
        project_id="proj_alpha",
        command="pytest",
        exit_code=1,
        error_message="KeyError: 'database_host'",
    )
    auth = AuthorizationContext(user_id="u1", project_id="proj_alpha")

    # Strict threshold 0.85 should exclude moderate match
    result_strict = retrieve_memory(req, auth, repository=repo, threshold=0.85)
    assert len(result_strict.project_matches) == 0

    # Permissive threshold 0.40 should include it
    result_permissive = retrieve_memory(req, auth, repository=repo, threshold=0.40)
    assert len(result_permissive.project_matches) == 1


def test_empty_repository_and_unknown_errors_safe():
    """Empty repository and missing fields must not raise uncaught exceptions."""
    repo = InMemoryIncidentRepository([])
    req = DiagnosisRequest(
        event_id="evt_empty",
        project_id="proj_empty",
        command="echo ok",
        exit_code=0,
        error_message="UnknownError: unrecognized exit status",
    )
    auth = AuthorizationContext(user_id="u_empty", project_id="proj_empty")

    result = retrieve_memory(req, auth, repository=repo, threshold=0.60)
    assert isinstance(result.all_ranked_matches, list)
    assert len(result.project_matches) == 0
    assert len(result.cross_project_matches) == 0


def test_fault_isolation_across_memory_levels():
    """If one level encounters an unexpected exception, other levels still execute."""
    class FaultyRepository:
        def get_project_incidents(self, project_id: str):
            raise RuntimeError("Database connection dropped during project retrieval!")

        def get_cross_project_incidents(self, requesting_project_id: str):
            return []

    req = DiagnosisRequest(
        event_id="evt_fault",
        project_id="proj_alpha",
        command="python app.py",
        exit_code=1,
        error_message="ModuleNotFoundError: No module named 'pydantic'",
    )
    auth = AuthorizationContext(user_id="u1", project_id="proj_alpha")

    # Should not raise RuntimeError; Level 1 should still succeed!
    result = retrieve_memory(req, auth, repository=FaultyRepository(), threshold=0.50)
    assert len(result.general_matches) >= 1
    assert len(result.project_matches) == 0
