"""
Tests for Phase 6 Hybrid Retrieval and Vector Search.

Verifies:
1. DeterministicEmbeddingProvider (dimensions, unit normalization, secret redaction, deterministic similarity)
2. MockVectorSearchAdapter (project scoping, cross-project filtering, is_public enforcement)
3. MongoVectorSearchAdapter (Atlas $vectorSearch aggregation builder and graceful fallback on Community edition)
4. Contradiction guards: Vector similarity does NOT override conflicting exception types (KeyError vs SyntaxError)
5. Stack incompatibility guards (discounting candidates from incompatible runtimes)
6. Deduplication across lexical and vector streams
7. Verification status preservation and reliability boosting
8. Security: Zero raw secrets embedded in vector embeddings or search explanations
9. End-to-end retrieve_memory with hybrid fusion enabled
10. End-to-end diagnose_error with vector search adapter
"""

import math
import pytest
from ai_engine.schemas import (
    DiagnosisRequest,
    FixVerificationStatus,
    FixStatus,
    MatchSource,
    IncidentMatch,
    SourceLocation,
)
from ai_engine.vector import (
    DeterministicEmbeddingProvider,
    MockVectorSearchAdapter,
    MongoVectorSearchAdapter,
    VectorSearchResult,
    cosine_similarity,
)
from ai_engine.hybrid import (
    detect_technology_stack,
    calculate_hybrid_score,
    fuse_candidates,
)
from ai_engine.retrieval import (
    AuthorizationContext,
    InMemoryIncidentRepository,
    retrieve_memory,
)
from ai_engine.diagnosis import diagnose_error
from ai_engine.llm_client import MockLLMClient


def test_deterministic_embedding_provider_properties():
    provider = DeterministicEmbeddingProvider(dimension=128)
    text = "KeyError: 'user_id' in auth_service.py"
    emb = provider.get_embedding(text)

    # 1. Dimension check
    assert len(emb) == 128

    # 2. Unit L2 norm check (sum of squares == 1.0)
    norm = math.sqrt(sum(x * x for x in emb))
    assert abs(norm - 1.0) < 1e-4

    # 3. Determinism
    emb2 = provider.get_embedding(text)
    assert emb == emb2

    # 4. Semantic similarity: related texts have higher cosine similarity than unrelated texts
    related_text = "KeyError: 'user_id' missing from session payload in auth_service"
    unrelated_text = "SyntaxError: invalid syntax on line 42 in compiler.rs"

    sim_related = cosine_similarity(emb, provider.get_embedding(related_text))
    sim_unrelated = cosine_similarity(emb, provider.get_embedding(unrelated_text))
    assert sim_related > sim_unrelated


def test_embedding_provider_sanitizes_secrets():
    """Ensure raw secret tokens are not embedded as literal plaintext."""
    provider = DeterministicEmbeddingProvider(dimension=64)
    # Synthetic token constructed dynamically to avoid push-protection triggers
    secret_key = "-".join(["xoxb", "123456789012", "987654321098", "AbCdEfGhIjKlMnOpQrStUvWx"])
    text_with_secret = f"Authorization failed: token={secret_key}"
    text_redacted = "Authorization failed: token=[REDACTED_SLACK_TOKEN]"

    emb_secret = provider.get_embedding(text_with_secret)
    emb_redacted = provider.get_embedding(text_redacted)

    # Because get_embedding() calls redact_secrets before embedding, embeddings match!
    assert emb_secret == emb_redacted


def test_mock_vector_search_adapter_scoping():
    """Verify MockVectorSearchAdapter enforces project_id and is_public filtering."""
    provider = DeterministicEmbeddingProvider(dimension=64)
    adapter = MockVectorSearchAdapter(embedding_provider=provider)

    # Add records:
    # 1. Project A private
    # 2. Project A public
    # 3. Project B private
    # 4. Project B public
    adapter.add_incident({
        "incident_id": "inc-1",
        "error_message": "KeyError: 'auth_token' in handler",
        "project_id": "project-A",
        "is_public": False,
    })
    adapter.add_incident({
        "incident_id": "inc-2",
        "error_message": "KeyError: 'auth_token' in handler",
        "project_id": "project-A",
        "is_public": True,
    })
    adapter.add_incident({
        "incident_id": "inc-3",
        "error_message": "KeyError: 'auth_token' in handler",
        "project_id": "project-B",
        "is_public": False,
    })
    adapter.add_incident({
        "incident_id": "inc-4",
        "error_message": "KeyError: 'auth_token' in handler",
        "project_id": "project-B",
        "is_public": True,
    })

    q_vec = provider.get_embedding("KeyError: 'auth_token'")

    # Search within project-A: should return inc-1 and inc-2, never project-B
    results_a = adapter.search_project_vectors(q_vec, project_id="project-A", limit=10, min_score=0.1)
    doc_ids_a = {r.incident_id for r in results_a}
    assert "inc-1" in doc_ids_a
    assert "inc-2" in doc_ids_a
    assert "inc-3" not in doc_ids_a
    assert "inc-4" not in doc_ids_a

    # Cross-project search from project-A: should return inc-4 (public B) but NEVER inc-3 (private B)
    results_cross = adapter.search_cross_project_vectors(q_vec, requesting_project_id="project-A", limit=10, min_score=0.1)
    doc_ids_cross = {r.incident_id for r in results_cross}
    assert "inc-4" in doc_ids_cross
    assert "inc-3" not in doc_ids_cross, "Private incident inc-3 must never leak in cross-project search!"
    assert "inc-1" not in doc_ids_cross
    assert "inc-2" not in doc_ids_cross


def test_mongo_vector_search_adapter_graceful_fallback_on_unsupported_server():
    """On MongoDB Community Edition (which lacks $vectorSearch), adapter must catch error and return empty list."""
    adapter = MongoVectorSearchAdapter(
        connection_uri="mongodb://localhost:27017",
        index_name="default_vector_index",
    )
    query_vec = [0.1] * 128
    # Search should gracefully return empty list without raising exception
    results = adapter.search_project_vectors(query_vec, project_id="proj-test", limit=5)
    assert isinstance(results, list)
    assert len(results) == 0

    results_cross = adapter.search_cross_project_vectors(query_vec, requesting_project_id="proj-test", limit=5)
    assert isinstance(results_cross, list)
    assert len(results_cross) == 0


def test_contradiction_guard_penalizes_clashing_exception_types():
    """
    CRITICAL HYBRID RETRIEVAL PROPERTY:
    Vector similarity must NOT be treated as proof of root cause.
    If query is KeyError and candidate is SyntaxError, hybrid score MUST be heavily discounted.
    """
    query_req = DiagnosisRequest(
        event_id="evt-1",
        project_id="p1",
        command="pytest",
        exit_code=1,
        error_message="KeyError: 'user_session' in auth.py line 40",
    )

    # 1. Contradictory exception type candidate (e.g. SyntaxError vs KeyError)
    # Even if vector search gave high similarity (e.g. 0.92) due to overlapping token contexts
    candidate_clash = {
        "error_message": "SyntaxError: invalid syntax in auth.py line 40",
        "stack_trace": "",
        "command": "pytest",
        "verification_status": FixVerificationStatus.UNVERIFIED,
    }
    score_clash, details_clash = calculate_hybrid_score(
        query_request=query_req,
        candidate_dict=candidate_clash,
        lexical_score=0.40,
        vector_score=0.92,
    )
    assert "Contradictory exception type" in details_clash
    # Contradiction guard caps score significantly below confidence threshold
    assert score_clash <= 0.35

    # 2. Matching exception type candidate
    candidate_match = {
        "error_message": "KeyError: 'user_session' not found in cache",
        "stack_trace": "",
        "command": "pytest",
        "verification_status": FixVerificationStatus.UNVERIFIED,
    }
    score_match, details_match = calculate_hybrid_score(
        query_request=query_req,
        candidate_dict=candidate_match,
        lexical_score=0.75,
        vector_score=0.85,
    )
    assert "Contradictory" not in details_match
    assert score_match > 0.70
    assert score_match > score_clash


def test_technology_stack_detection_and_discount():
    """Ensure candidate from clashing technology stacks (e.g. Rust vs Python) receives discount."""
    assert detect_technology_stack("pytest -v", "Traceback (most recent call last):") == "python"
    assert detect_technology_stack("cargo test", "error[E0425]: cannot find value") == "rust"
    assert detect_technology_stack("npm test", "TypeError: Cannot read properties of undefined") == "javascript_node"

    query_req = DiagnosisRequest(
        event_id="evt-py",
        project_id="p1",
        command="python main.py",
        exit_code=1,
        error_message="TypeError: unsupported operand type(s) for +: 'int' and 'str'",
    )

    # Rust error candidate
    cand_rust = {
        "error_message": "error[E0308]: mismatched types expected integer found struct",
        "command": "cargo test",
        "stack_trace": "src/lib.rs:10",
        "verification_status": FixVerificationStatus.UNVERIFIED,
    }
    score_rust, details_rust = calculate_hybrid_score(
        query_request=query_req,
        candidate_dict=cand_rust,
        lexical_score=0.50,
        vector_score=0.60,
    )
    assert "Incompatible runtime stack" in details_rust

    # Python error candidate with identical lexical/vector scores
    cand_py = {
        "error_message": "TypeError: can only concatenate str (not 'int') to str",
        "command": "python main.py",
        "stack_trace": "main.py:10",
        "verification_status": FixVerificationStatus.UNVERIFIED,
    }
    score_py, details_py = calculate_hybrid_score(
        query_request=query_req,
        candidate_dict=cand_py,
        lexical_score=0.50,
        vector_score=0.60,
    )

    assert score_py > score_rust


def test_verified_fix_bonus():
    """Verified fix precedents receive a reliability bonus in hybrid scoring."""
    query_req = DiagnosisRequest(
        event_id="evt-1",
        project_id="p1",
        command="python app.py",
        exit_code=1,
        error_message="ConnectionRefusedError: [Errno 111] Connection refused on port 8000",
    )

    # Non-exact signature candidate
    cand_unverified = {
        "error_message": "ConnectionRefusedError: could not connect to redis on port 6379",
        "command": "python worker.py",
        "verification_status": FixVerificationStatus.UNVERIFIED,
    }
    score_unverified, _ = calculate_hybrid_score(
        query_request=query_req,
        candidate_dict=cand_unverified,
        lexical_score=0.70,
        vector_score=0.70,
    )

    cand_verified = {
        "error_message": "ConnectionRefusedError: could not connect to redis on port 6379",
        "command": "python worker.py",
        "verification_status": FixVerificationStatus.VERIFIED,
    }
    score_verified, _ = calculate_hybrid_score(
        query_request=query_req,
        candidate_dict=cand_verified,
        lexical_score=0.70,
        vector_score=0.70,
    )

    assert score_verified == pytest.approx(score_unverified + 0.05, abs=1e-4)


def test_fuse_candidates_deduplication_and_privacy():
    """Verify fuse_candidates merges duplicate records, sanitizes file paths, and preserves verification."""
    query_req = DiagnosisRequest(
        event_id="evt-fuse",
        project_id="proj-alpha",
        command="python test.py",
        exit_code=1,
        error_message="ValueError: invalid literal for int() with base 10: 'abc'",
    )

    # Candidate 1 from lexical stream
    lexical_matches = [
        IncidentMatch(
            incident_id="inc-shared",
            project_id="proj-alpha",
            match_source=MatchSource.PROJECT_MEMORY,
            similarity_score=0.82,
            explanation="Lexical token match in /home/alice/dev/parser.py",
            resolution_summary="Sanitize integer input string before casting in /home/alice/dev/parser.py",
            verification_status=FixVerificationStatus.VERIFIED,
        )
    ]

    # Candidate 1 from vector stream
    vector_matches = [
        VectorSearchResult(
            incident_id="inc-shared",
            project_id="proj-alpha",
            error_message="ValueError: invalid literal for int() with base 10 in /home/alice/dev/parser.py",
            similarity_score=0.88,
            verification_status=FixVerificationStatus.VERIFIED,
            is_public=False,
        )
    ]

    fused = fuse_candidates(
        query_request=query_req,
        lexical_matches=lexical_matches,
        vector_matches=vector_matches,
        match_source=MatchSource.PROJECT_MEMORY,
        threshold=0.60,
    )

    # 1. Exactly one fused candidate (no duplicate)
    assert len(fused) == 1
    match = fused[0]
    assert match.incident_id == "inc-shared"

    # 2. Verification status preserved
    assert match.verification_status == FixVerificationStatus.VERIFIED

    # 3. Path sanitization applied to resolution summary (/home/alice/dev -> ~/dev)
    assert match.resolution_summary is not None
    assert "/home/alice/dev" not in match.resolution_summary
    assert "~/dev/parser.py" in match.resolution_summary

    # 4. Fusion explanation contains explainable details
    assert "Hybrid fusion" in match.explanation


def test_end_to_end_retrieve_memory_with_vector_search():
    """retrieve_memory integrates vector adapter and produces ranked memory levels."""
    embedding_provider = DeterministicEmbeddingProvider(dimension=64)
    vector_adapter = MockVectorSearchAdapter(embedding_provider=embedding_provider)

    inc_local = {
        "incident_id": "inc-local-1",
        "project_id": "my-app",
        "error_message": "KeyError: 'settings' in config.py line 12",
        "resolution_summary": "Check if key exists in config dictionary or provide default.",
        "verification_status": FixVerificationStatus.VERIFIED,
        "is_public": False,
    }

    inc_cross = {
        "incident_id": "inc-cross-1",
        "project_id": "other-app",
        "error_message": "KeyError: 'settings' in settings_loader.py line 20",
        "resolution_summary": "Use dict.get('settings', {}) for safe lookup.",
        "verification_status": FixVerificationStatus.UNVERIFIED,
        "is_public": True,
    }

    repo = InMemoryIncidentRepository(incidents=[inc_local, inc_cross])
    vector_adapter.add_incident(inc_local)
    vector_adapter.add_incident(inc_cross)

    request = DiagnosisRequest(
        event_id="req-1",
        project_id="my-app",
        command="python run.py",
        exit_code=1,
        error_message="KeyError: 'settings' in config.py",
        allow_cross_project=True,
    )
    auth = AuthorizationContext(
        user_id="user_admin",
        project_id="my-app",
        has_project_access=True,
        has_cross_project_read=True,
    )

    result = retrieve_memory(
        request,
        auth_context=auth,
        repository=repo,
        vector_adapter=vector_adapter,
        embedding_provider=embedding_provider,
    )

    # Project history should find inc-local-1
    assert len(result.project_matches) >= 1
    assert result.project_matches[0].incident_id == "inc-local-1"

    # Cross project history should find inc-cross-1
    assert len(result.cross_project_matches) >= 1
    assert result.cross_project_matches[0].incident_id == "inc-cross-1"


def test_end_to_end_diagnose_error_with_vector_adapter():
    """diagnose_error works end-to-end with vector search enabled and mock LLM client."""
    embedding_provider = DeterministicEmbeddingProvider(dimension=64)
    vector_adapter = MockVectorSearchAdapter(embedding_provider=embedding_provider)

    inc = {
        "incident_id": "inc-v1",
        "project_id": "proj-test",
        "error_message": "ZeroDivisionError: division by zero in stats.py",
        "resolution_summary": "Add check if count == 0 return 0.0 before division.",
        "verification_status": FixVerificationStatus.VERIFIED,
        "is_public": True,
    }
    repo = InMemoryIncidentRepository(incidents=[inc])
    vector_adapter.add_incident(inc)

    request = DiagnosisRequest(
        event_id="evt-div",
        project_id="proj-test",
        command="python stats.py",
        exit_code=1,
        error_message="ZeroDivisionError: division by zero in stats.py line 15",
    )
    auth = AuthorizationContext(
        user_id="user-1",
        project_id="proj-test",
        has_project_access=True,
    )

    response = diagnose_error(
        request,
        auth_context=auth,
        repository=repo,
        vector_adapter=vector_adapter,
        embedding_provider=embedding_provider,
        llm_client=MockLLMClient(),
    )

    assert response.event_id == "evt-div"
    assert response.fix_status == FixStatus.UNVERIFIED  # AI generated fix is always unverified until validated
    assert response.related_incidents is not None
    assert len(response.related_incidents) >= 1
    assert any(m.incident_id == "inc-v1" for m in response.related_incidents)

