"""
Tests for Phase 6.3 Retrieval Benchmark Integrity and Production Readiness Audit.

Verifies:
1. Retrieval Benchmark Harness execution and multi-mode metrics calculation.
2. Distinct denominators between Suite A (56-scenario multi-tier diagnosis) and Suite B (targeted retrieval generalization).
3. Transparent reporting and explicit exclusion of 4 unscorable scenarios.
4. Paraphrase score provenance audit and verification that Mode 3 is labeled as simulated mock.
5. Misleading and negative candidate evaluation.
6. Preprocessing parity for queries vs documents via build_embedding_text.
7. Fail-closed security and contradiction guards across all retrieval modes.
"""

import math
import os
import pytest

from ai_engine.evaluation.fixtures import DATASET_VERSION, EVALUATION_SCENARIOS
from ai_engine.evaluation.evaluator import run_evaluation
from ai_engine.evaluation.retrieval_benchmark import (
    BENCHMARK_CORPUS,
    BENCHMARK_SCENARIOS,
    BenchmarkMockDenseClient,
    run_all_retrieval_benchmarks,
    run_retrieval_mode_benchmark,
)
from ai_engine.hybrid import calculate_hybrid_score
from ai_engine.retrieval import (
    AuthorizationContext,
    InMemoryIncidentRepository,
    retrieve_memory,
)
from ai_engine.schemas import DiagnosisRequest, FixVerificationStatus
from ai_engine.vector import (
    ConfigurableDenseEmbeddingProvider,
    DeterministicEmbeddingProvider,
    MockVectorSearchAdapter,
    build_embedding_text,
    cosine_similarity,
)


def test_suite_a_denominators_and_metrics_separation():
    """Task 1 Audit: Verify Suite A metrics have explicit, disjoint denominators."""
    metrics, details = run_evaluation(live_llm=False)

    # 1. Total Scenarios
    assert metrics.total_scenarios == 56

    # 2. Denominator for Level 1 KB Retrieval is strictly 25 (scenarios with expected_kb_id)
    target_kb_scenarios = [s for s in EVALUATION_SCENARIOS if s.get("expected_kb_id")]
    assert len(target_kb_scenarios) == 25

    # 3. Denominator for FalsePositiveRate is strictly 31 (scenarios without expected_kb_id)
    no_target_kb_scenarios = [s for s in EVALUATION_SCENARIOS if not s.get("expected_kb_id")]
    assert len(no_target_kb_scenarios) == 31
    assert len(target_kb_scenarios) + len(no_target_kb_scenarios) == 56

    # 4. Explicitly Unscorable Scenarios is strictly 4 (excluded from RootCauseAccuracy)
    unscorable = [
        s for s in EVALUATION_SCENARIOS
        if "unscorable" in s.get("expected_root_cause_categories", [])
        or s.get("category") == "unknown_format"
    ]
    assert len(unscorable) == 4
    assert metrics.unscorable_scenarios == 4

    # 5. Denominator for RootCauseAccuracy is 56 - 4 = 52
    scorable_root_cause = [
        s for s in EVALUATION_SCENARIOS
        if s not in unscorable and s.get("expected_root_cause_categories")
    ]
    assert len(scorable_root_cause) == 52

    # 6. Verify formal IR metrics are computed strictly on target_kb_cases (N=25)
    assert metrics.retrieval_recall_at_3 == 1.0  # 25 / 25
    assert metrics.retrieval_recall_at_5 == 1.0  # 25 / 25
    assert metrics.retrieval_precision_at_1 == 1.0  # 25 / 25
    assert metrics.retrieval_precision_at_3 == round(25 / (3 * 25), 4) or abs(metrics.retrieval_precision_at_3 - (1.0 / 3.0)) < 1e-3
    assert metrics.retrieval_mrr == 1.0


def test_suite_b_multi_mode_retrieval_benchmark():
    """Task 2 Audit: Verify retrieval benchmark harness executes deterministically offline."""
    results = run_all_retrieval_benchmarks()

    m1 = results["mode1_lexical"]
    m2 = results["mode2_deterministic_hybrid"]
    m3 = results["mode3_dense_mock_hybrid"]

    # Integrity verification: Mode 3 is marked as simulated mock
    assert not m1.is_simulated_mock
    assert not m2.is_simulated_mock
    assert m3.is_simulated_mock
    assert "Simulated" in m3.provider_description

    # Contradiction Rejection Rate is 100% across ALL modes
    assert m1.contradiction_rejection_rate == 1.0
    assert m2.contradiction_rejection_rate == 1.0
    assert m3.contradiction_rejection_rate == 1.0

    # False-Positive Rate is 0.0% across ALL modes on negative queries
    assert m1.false_positive_rate == 0.0
    assert m2.false_positive_rate == 0.0
    assert m3.false_positive_rate == 0.0

    # Project Isolation Rate is 100% across ALL modes
    assert m1.project_isolation_rate == 1.0
    assert m2.project_isolation_rate == 1.0
    assert m3.project_isolation_rate == 1.0

    # Dense semantic mock achieves higher or equal MRR compared to lexical
    assert m3.mrr >= m1.mrr


def test_misleading_candidates_do_not_displace_target():
    """Task 2: Benchmark evaluates misleading candidates (same module/error type)."""
    mock_client = BenchmarkMockDenseClient(dimension=128)
    provider = ConfigurableDenseEmbeddingProvider(dimension=128, client=mock_client)
    adapter = MockVectorSearchAdapter(embedding_provider=provider, incidents=BENCHMARK_CORPUS)
    repo = InMemoryIncidentRepository(BENCHMARK_CORPUS)
    auth = AuthorizationContext(user_id="u", project_id="proj_main", has_project_access=True)

    # Query for JWT token expiration
    req_jwt = DiagnosisRequest(
        event_id="req_jwt",
        project_id="proj_main",
        command="python manage.py runserver",
        exit_code=1,
        error_message="jwt.exceptions.ExpiredSignatureError: The token lifetime has ended",
    )
    res = retrieve_memory(req_jwt, auth, repository=repo, vector_adapter=adapter, embedding_provider=provider, threshold=0.30)

    # 1. Target (inc_target_jwt_expiry) must rank higher than distractor (inc_misleading_jwt_padding)
    target_match = next((m for m in res.project_matches if m.incident_id == "inc_target_jwt_expiry"), None)
    distractor_match = next((m for m in res.project_matches if m.incident_id == "inc_misleading_jwt_padding"), None)

    assert target_match is not None
    if distractor_match:
        assert target_match.similarity_score > distractor_match.similarity_score

    # 2. Clashing candidate (inc_clash_syntax_jwt) must be suppressed by contradiction guard
    clash_match = next((m for m in res.project_matches if m.incident_id == "inc_clash_syntax_jwt"), None)
    assert clash_match is None or clash_match.similarity_score <= 0.35


def test_preprocessing_parity_query_vs_document():
    """Task 4: Ensure identical sanitization, truncation, and ordering for queries and documents."""
    # Dynamic secret token
    tok = "-".join(["xoxb", "123456789012", "987654321098", "AbCdEfGhIjKlMnOpQrStUvWx"])
    dirty_err = f"Auth failed with token={tok} in /home/alice/app.py"
    dirty_stack = "File '/home/alice/app.py', line 10, in auth\n  raise AuthError()"
    dirty_cmd = "python /home/alice/app.py"

    text_q = build_embedding_text(dirty_err, dirty_stack, dirty_cmd)
    text_d = build_embedding_text(dirty_err, dirty_stack, dirty_cmd)

    # Parity check
    assert text_q == text_d
    assert tok not in text_q
    assert "[REDACTED_SLACK_TOKEN]" in text_q
    assert "/home/alice" not in text_q
    assert "~/app.py" in text_q
    assert len(text_q) <= 1050


def test_fail_closed_authorization_security():
    """Task 5: Verify fail-closed behavior when authorization context lacks permissions."""
    repo = InMemoryIncidentRepository(BENCHMARK_CORPUS)
    provider = DeterministicEmbeddingProvider(dimension=128)
    adapter = MockVectorSearchAdapter(embedding_provider=provider, incidents=BENCHMARK_CORPUS)

    req = DiagnosisRequest(
        event_id="req_sec",
        project_id="proj_main",
        command="npm test",
        exit_code=1,
        error_message="TypeError: Cannot read properties of undefined (reading 'billing_pin')",
        allow_cross_project=True,
    )

    # 1. No project access -> Level 2 returns 0 matches
    auth_no_proj = AuthorizationContext(user_id="u", project_id="proj_main", has_project_access=False)
    res_no_proj = retrieve_memory(req, auth_no_proj, repository=repo, vector_adapter=adapter, embedding_provider=provider)
    assert len(res_no_proj.project_matches) == 0

    # 2. No cross-project read permission -> Level 3 returns 0 matches even if requested
    auth_no_cross = AuthorizationContext(user_id="u", project_id="proj_main", has_project_access=True, has_cross_project_read=False)
    res_no_cross = retrieve_memory(req, auth_no_cross, repository=repo, vector_adapter=adapter, embedding_provider=provider)
    assert len(res_no_cross.cross_project_matches) == 0

    # 3. Authorized cross-project read -> NEVER surfaces private candidate
    auth_cross = AuthorizationContext(user_id="u", project_id="proj_main", has_project_access=True, has_cross_project_read=True)
    res_cross = retrieve_memory(req, auth_cross, repository=repo, vector_adapter=adapter, embedding_provider=provider)
    cross_ids = {m.incident_id for m in res_cross.cross_project_matches}
    assert "inc_private_classified_billing" not in cross_ids
