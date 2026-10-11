"""
Tests for Phase 6.8: Language-Aware Exception Taxonomy and Safe Contradiction Handling.

Verifies:
1. Exact exception-type matches.
2. Known subtype-compatible exception types (e.g. ModuleNotFoundError < ImportError).
3. Truly incompatible exception types (e.g. SyntaxError vs KeyError, sibling OSErrors).
4. Unknown or missing exception types.
5. Similar error messages with incompatible root causes.
6. Runtime and language mismatches (e.g. Node TypeError vs Python TypeError).
7. Malformed exception metadata and extreme inputs.
8. Cross-project retrieval with missing authorization.
9. Private incidents with high similarity strictly preserved as secret.
10. Ranking behavior when exact, compatible, and contradictory candidates coexist.
11. Verification status independence from exception compatibility.
"""

import pytest

from ai_engine.hybrid import calculate_hybrid_score, fuse_candidates
from ai_engine.matching import extract_exception_type
from ai_engine.retrieval import (
    AuthorizationContext,
    InMemoryIncidentRepository,
    retrieve_memory,
)
from ai_engine.schemas import (
    DiagnosisRequest,
    FixVerificationStatus,
    IncidentMatch,
    MatchSource,
)
from ai_engine.taxonomy import (
    ExceptionCompatibility,
    PYTHON_EXCEPTION_HIERARCHY,
    detect_runtime_language,
    evaluate_exception_compatibility,
    get_python_ancestors,
    is_python_subtype_compatible,
    normalize_exception_identifier,
)
from ai_engine.vector import (
    ConfigurableDenseEmbeddingProvider,
    DeterministicEmbeddingProvider,
    MockVectorSearchAdapter,
)


def test_exact_exception_type_matches():
    """Verify identical exception identifiers evaluate to EXACT compatibility."""
    assert evaluate_exception_compatibility("TypeError", "TypeError") == ExceptionCompatibility.EXACT
    assert evaluate_exception_compatibility("KeyError", "KeyError") == ExceptionCompatibility.EXACT
    assert evaluate_exception_compatibility("SyntaxError", "SyntaxError") == ExceptionCompatibility.EXACT

    # Qualified module stripping parity
    assert evaluate_exception_compatibility(
        "psycopg2.OperationalError", "OperationalError"
    ) == ExceptionCompatibility.EXACT
    assert evaluate_exception_compatibility(
        "jwt.exceptions.ExpiredSignatureError", "ExpiredSignatureError"
    ) == ExceptionCompatibility.EXACT


def test_known_subtype_compatible_exception_types():
    """Verify Python ModuleNotFoundError is recognized as subtype-compatible with ImportError."""
    # Child -> Parent
    assert evaluate_exception_compatibility(
        "ModuleNotFoundError", "ImportError", query_command="python run.py", candidate_command="python run.py"
    ) == ExceptionCompatibility.SUBTYPE

    # Parent -> Child
    assert evaluate_exception_compatibility(
        "ImportError", "ModuleNotFoundError", query_command="python run.py", candidate_command="python run.py"
    ) == ExceptionCompatibility.SUBTYPE

    # Connection hierarchy: ConnectionRefusedError < ConnectionError < OSError
    assert evaluate_exception_compatibility(
        "ConnectionRefusedError", "ConnectionError", query_command="python app.py"
    ) == ExceptionCompatibility.SUBTYPE
    assert evaluate_exception_compatibility(
        "ConnectionRefusedError", "OSError", query_command="python app.py"
    ) == ExceptionCompatibility.SUBTYPE

    # Go panic normalization equivalence
    go_panic_1 = "panic: runtime error: nil pointer dereference in handler.go"
    go_panic_2 = "panic: runtime error: invalid memory address or nil pointer dereference at handler.go:88"
    assert evaluate_exception_compatibility(
        go_panic_1, go_panic_2, query_command="go test ./...", candidate_command="go test ./..."
    ) == ExceptionCompatibility.EQUIVALENT


def test_truly_incompatible_exception_types():
    """Verify genuinely conflicting exceptions are marked INCOMPATIBLE and penalized."""
    # Classical syntax vs runtime clashes
    assert evaluate_exception_compatibility("SyntaxError", "KeyError") == ExceptionCompatibility.INCOMPATIBLE
    assert evaluate_exception_compatibility("OperationalError", "SyntaxError") == ExceptionCompatibility.INCOMPATIBLE
    assert evaluate_exception_compatibility("TypeError", "ValueError") == ExceptionCompatibility.INCOMPATIBLE

    # Sibling exceptions under LookupError: KeyError and IndexError MUST NOT be compatible
    assert evaluate_exception_compatibility(
        "KeyError", "IndexError", query_command="python app.py"
    ) == ExceptionCompatibility.INCOMPATIBLE

    # Sibling exceptions under OSError: FileNotFoundError and PermissionError MUST NOT be compatible
    assert evaluate_exception_compatibility(
        "FileNotFoundError", "PermissionError", query_command="python app.py"
    ) == ExceptionCompatibility.INCOMPATIBLE


def test_unknown_or_missing_exception_types():
    """Verify missing or unidentifiable exception types evaluate conservatively as UNKNOWN."""
    assert evaluate_exception_compatibility(None, "TypeError") == ExceptionCompatibility.UNKNOWN
    assert evaluate_exception_compatibility("SyntaxError", None) == ExceptionCompatibility.UNKNOWN
    assert evaluate_exception_compatibility("", "") == ExceptionCompatibility.UNKNOWN
    assert evaluate_exception_compatibility(None, None) == ExceptionCompatibility.UNKNOWN


def test_similar_error_messages_with_incompatible_root_causes():
    """Verify contradiction guard penalizes candidates sharing text/paths but with conflicting exception types."""
    query_req = DiagnosisRequest(
        event_id="evt_test_clash",
        project_id="proj_1",
        command="python worker.py",
        exit_code=1,
        error_message="FileNotFoundError: [Errno 2] No such file or directory: '/var/log/app/worker.log'",
    )

    # Candidate with the exact same file path and command, but PermissionError
    candidate_permission = {
        "error_message": "PermissionError: [Errno 13] Permission denied: '/var/log/app/worker.log'",
        "stack_trace": "",
        "command": "python worker.py",
        "verification_status": FixVerificationStatus.VERIFIED,
    }

    score, explanation = calculate_hybrid_score(
        query_request=query_req,
        candidate_dict=candidate_permission,
        lexical_score=0.85,
        vector_score=0.95,
    )

    # Contradiction guard must activate and cap score to <= 0.35 despite 0.95 vector score
    assert "Contradictory exception type" in explanation
    assert score <= 0.35


def test_runtime_and_language_mismatches():
    """Verify cross-language runtime mismatches evaluate as INCOMPATIBLE even with identical exception names."""
    # Query is Node.js TypeError; candidate is Python TypeError
    assert evaluate_exception_compatibility(
        query_type="TypeError",
        candidate_type="TypeError",
        query_command="node server.js",
        query_stack="at Object.<anonymous> (/app/index.js:10:5)",
        candidate_command="python app.py",
        candidate_stack='File "app.py", line 10, in <module>',
    ) == ExceptionCompatibility.INCOMPATIBLE

    # Query is Python, candidate is Go panic
    assert evaluate_exception_compatibility(
        query_type="ModuleNotFoundError",
        candidate_type="panic: runtime error: nil pointer dereference",
        query_command="python run.py",
        candidate_command="go run main.go",
    ) == ExceptionCompatibility.INCOMPATIBLE


def test_malformed_exception_metadata():
    """Verify robustness against malformed, adversarial, or oversized exception strings."""
    huge_str = "Error " * 500
    res = evaluate_exception_compatibility(huge_str, "KeyError")
    assert res in (ExceptionCompatibility.INCOMPATIBLE, ExceptionCompatibility.UNKNOWN)

    # Special regex characters
    res_regex = evaluate_exception_compatibility(".*+?[]()", "^$$")
    assert res_regex in (ExceptionCompatibility.INCOMPATIBLE, ExceptionCompatibility.UNKNOWN)


def test_ranking_behavior_when_compatible_and_contradictory_candidates_coexist():
    """Verify ranking order: Exact Match > Subtype Compatible > Contradictory Candidate."""
    query_req = DiagnosisRequest(
        event_id="evt_hierarchy_rank",
        project_id="proj_py",
        command="python run.py",
        exit_code=1,
        error_message="ModuleNotFoundError: No module named 'yaml'",
    )

    # 1. Exact match candidate (ModuleNotFoundError)
    cand_exact = {
        "error_message": "ModuleNotFoundError: No module named 'yaml' in virtualenv",
        "command": "python run.py",
        "verification_status": FixVerificationStatus.VERIFIED,
    }
    score_exact, _ = calculate_hybrid_score(
        query_request=query_req, candidate_dict=cand_exact, lexical_score=0.80, vector_score=0.90
    )

    # 2. Subtype compatible candidate (ImportError)
    cand_subtype = {
        "error_message": "ImportError: PyYAML package is not installed in virtual environment",
        "command": "python run.py",
        "verification_status": FixVerificationStatus.VERIFIED,
    }
    score_subtype, details_sub = calculate_hybrid_score(
        query_request=query_req, candidate_dict=cand_subtype, lexical_score=0.0, vector_score=0.90
    )

    # 3. Contradictory candidate (SyntaxError)
    cand_clash = {
        "error_message": "SyntaxError: invalid syntax in yaml_loader.py line 4",
        "command": "python run.py",
        "verification_status": FixVerificationStatus.VERIFIED,
    }
    score_clash, details_clash = calculate_hybrid_score(
        query_request=query_req, candidate_dict=cand_clash, lexical_score=0.20, vector_score=0.90
    )

    # Invariants:
    # Exact match > Subtype match > Contradictory match
    assert score_exact > score_subtype
    assert score_subtype > score_clash

    # Subtype match must clear retrieval threshold (>= 0.30)
    assert score_subtype >= 0.30
    assert "Compatible exception subtype" in details_sub

    # Contradictory match must be capped (<= 0.35)
    assert score_clash <= 0.35
    assert "Contradictory exception type" in details_clash


def test_cross_project_retrieval_with_missing_authorization():
    """Verify exception compatibility NEVER bypasses missing cross-project read authorization."""
    corpus = [
        {
            "incident_id": "inc_shared_mod",
            "project_id": "proj_external",
            "error_message": "ImportError: No module named 'yaml'",
            "command": "python run.py",
            "is_public": True,
            "verification_status": FixVerificationStatus.VERIFIED,
        }
    ]
    repo = InMemoryIncidentRepository(corpus)
    provider = DeterministicEmbeddingProvider(dimension=128)
    adapter = MockVectorSearchAdapter(embedding_provider=provider, incidents=corpus)

    req = DiagnosisRequest(
        event_id="evt_auth_denied",
        project_id="proj_local",
        command="python run.py",
        exit_code=1,
        error_message="ModuleNotFoundError: No module named 'yaml'",
        allow_cross_project=True,
    )

    # User context lacks has_cross_project_read
    auth_denied = AuthorizationContext(
        user_id="user_1", project_id="proj_local", has_project_access=True, has_cross_project_read=False
    )
    res = retrieve_memory(req, auth_denied, repository=repo, vector_adapter=adapter, embedding_provider=provider)

    # Level 3 must return 0 matches
    assert len(res.cross_project_matches) == 0


def test_private_incidents_with_high_similarity():
    """Verify private external incident is NEVER returned even with exact match and 1.0 vector score."""
    corpus = [
        {
            "incident_id": "inc_private_secret",
            "project_id": "proj_external",
            "error_message": "ModuleNotFoundError: No module named 'yaml'",
            "command": "python run.py",
            "is_public": False,  # STRICTLY PRIVATE
            "verification_status": FixVerificationStatus.VERIFIED,
        }
    ]
    repo = InMemoryIncidentRepository(corpus)
    provider = DeterministicEmbeddingProvider(dimension=128)
    adapter = MockVectorSearchAdapter(embedding_provider=provider, incidents=corpus)

    req = DiagnosisRequest(
        event_id="evt_private_leak_attempt",
        project_id="proj_local",
        command="python run.py",
        exit_code=1,
        error_message="ModuleNotFoundError: No module named 'yaml'",
        allow_cross_project=True,
    )

    # User has cross-project grant
    auth_granted = AuthorizationContext(
        user_id="user_1", project_id="proj_local", has_project_access=True, has_cross_project_read=True
    )
    res = retrieve_memory(req, auth_granted, repository=repo, vector_adapter=adapter, embedding_provider=provider)

    all_ids = {m.incident_id for m in res.all_ranked_matches}
    assert "inc_private_secret" not in all_ids


def test_verified_fix_status_independence_from_compatibility():
    """Verify compatible exception types do NOT fabricate verified fix status."""
    query_req = DiagnosisRequest(
        event_id="evt_status_check",
        project_id="proj_1",
        command="python run.py",
        exit_code=1,
        error_message="ModuleNotFoundError: No module named 'yaml'",
    )

    cand_unverified = {
        "error_message": "ImportError: No module named 'yaml'",
        "command": "python run.py",
        "verification_status": FixVerificationStatus.UNVERIFIED,
    }
    score, details = calculate_hybrid_score(
        query_request=query_req, candidate_dict=cand_unverified, lexical_score=0.8, vector_score=0.8
    )

    # Compatibility is confirmed, but verification status remains UNVERIFIED
    assert "Compatible exception subtype" in details
    assert "Precedent verified" not in details
