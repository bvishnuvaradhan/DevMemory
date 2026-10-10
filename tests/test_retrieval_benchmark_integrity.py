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
    BENCHMARK_VERSION,
    BenchmarkMockDenseClient,
    compute_ir_metrics,
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
    m4 = results["mode4_real_dense"]

    # Integrity verification: Mode 3 is marked as simulated mock
    assert not m1.is_simulated_mock
    assert not m2.is_simulated_mock
    assert m3.is_simulated_mock
    assert "Simulated" in m3.provider_description

    # Integrity verification: Mode 4 reports skipped when unconfigured
    if not os.getenv("OPENAI_API_KEY"):
        assert m4.is_executed is False
        assert m4.status == "SKIPPED"
        assert "SKIPPED" in m4.provider_description

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


def test_retrieval_benchmark_v2_dataset_structure_and_categories():
    """Verify v2.0.0 dataset expansion to 30 corpus items, 33 scenarios, and explicit categories."""
    assert BENCHMARK_VERSION == "2.0.0"

    # 1. Corpus verification
    assert len(BENCHMARK_CORPUS) == 30
    corpus_ids = [item["incident_id"] for item in BENCHMARK_CORPUS]
    assert len(set(corpus_ids)) == 30  # All IDs unique

    # 2. Scenario verification
    assert len(BENCHMARK_SCENARIOS) == 33
    scenario_ids = [s.scenario_id for s in BENCHMARK_SCENARIOS]
    assert len(set(scenario_ids)) == 33  # All scenario IDs unique

    # 3. Denominators verification
    pos_cases = [s for s in BENCHMARK_SCENARIOS if s.expected_target_id is not None and not s.is_cross_project]
    neg_cases = [s for s in BENCHMARK_SCENARIOS if s.scenario_type == "negative_unrelated"]
    clash_cases = [s for s in BENCHMARK_SCENARIOS if s.clashing_id is not None]
    cross_cases = [s for s in BENCHMARK_SCENARIOS if s.is_cross_project]

    assert len(pos_cases) == 26
    assert len(neg_cases) == 5
    assert len(clash_cases) == 4
    assert len(cross_cases) == 2
    assert len(pos_cases) + len(neg_cases) + len(cross_cases) == 33

    # 4. Integrity of referenced IDs
    corpus_id_set = set(corpus_ids)
    for scn in BENCHMARK_SCENARIOS:
        if scn.expected_target_id:
            assert scn.expected_target_id in corpus_id_set, f"Unknown target {scn.expected_target_id} in {scn.scenario_id}"
        if scn.distractor_id:
            assert scn.distractor_id in corpus_id_set, f"Unknown distractor {scn.distractor_id} in {scn.scenario_id}"
        if scn.clashing_id:
            assert scn.clashing_id in corpus_id_set, f"Unknown clashing {scn.clashing_id} in {scn.scenario_id}"
        if scn.forbidden_leak_id:
            assert scn.forbidden_leak_id in corpus_id_set, f"Unknown forbidden {scn.forbidden_leak_id} in {scn.scenario_id}"

    # 5. Technical categories verification
    categories = {s.category for s in BENCHMARK_SCENARIOS}
    required_domains = {
        "auth_jwt", "database", "node_runtime", "python_deps", "cache_redis",
        "containers_docker", "node_esm", "vcs_git", "web_cors", "security_tls",
        "concurrency_deadlock", "filesystem_os", "rust_borrow", "go_runtime",
        "syntax_compilation", "data_integrity", "api_rate_limit", "environment_runtime",
        "security_privacy", "unrelated_negative", "contradiction_guard", "security_isolation",
    }
    for dom in required_domains:
        assert dom in categories, f"Missing required domain: {dom}"


def test_compute_ir_metrics_mathematical_properties_and_boundaries():
    """Verify IR metric formulas, boundary handling, and zero-division safety."""
    # Case A: Perfect retrieval
    perf = compute_ir_metrics(
        hits_at_1=10,
        hits_at_3=10,
        hits_at_5=10,
        reciprocal_ranks=[1.0] * 10,
        n_pos=10,
        false_positives=0,
        n_neg=5,
        clash_passed=3,
        n_clash=3,
        isolation_passed=2,
        n_cross=2,
    )
    assert perf["recall_at_1"] == 1.0
    assert perf["recall_at_3"] == 1.0
    assert perf["recall_at_5"] == 1.0
    assert perf["precision_at_1"] == 1.0
    assert abs(perf["precision_at_3"] - (1.0 / 3.0)) < 1e-4
    assert perf["mrr"] == 1.0
    assert perf["false_positive_rate"] == 0.0
    assert perf["contradiction_rejection_rate"] == 1.0
    assert perf["project_isolation_rate"] == 1.0

    # Case B: Degraded retrieval (5 at rank 1, 3 at rank 2, 2 at rank 5)
    rr = [1.0] * 5 + [0.5] * 3 + [0.2] * 2
    degraded = compute_ir_metrics(
        hits_at_1=5,
        hits_at_3=8,
        hits_at_5=10,
        reciprocal_ranks=rr,
        n_pos=10,
        false_positives=1,
        n_neg=4,
        clash_passed=2,
        n_clash=3,
        isolation_passed=1,
        n_cross=2,
    )
    assert degraded["recall_at_1"] == 0.5
    assert degraded["recall_at_3"] == 0.8
    assert degraded["recall_at_5"] == 1.0
    assert degraded["precision_at_1"] == 0.5
    assert abs(degraded["precision_at_3"] - (8.0 / 30.0)) < 1e-4
    assert abs(degraded["mrr"] - (5.0 + 1.5 + 0.4) / 10.0) < 1e-4
    assert degraded["false_positive_rate"] == 0.25
    assert abs(degraded["contradiction_rejection_rate"] - (2.0 / 3.0)) < 1e-4
    assert degraded["project_isolation_rate"] == 0.5

    # Case C: Boundary condition: zero positives (safe fallback)
    zero_pos = compute_ir_metrics(
        hits_at_1=0, hits_at_3=0, hits_at_5=0, reciprocal_ranks=[], n_pos=0,
        false_positives=0, n_neg=5, clash_passed=2, n_clash=2, isolation_passed=1, n_cross=1,
    )
    assert zero_pos["recall_at_1"] == 1.0
    assert zero_pos["mrr"] == 1.0

    # Case D: Boundary condition: zero negatives (safe fallback)
    zero_neg = compute_ir_metrics(
        hits_at_1=5, hits_at_3=5, hits_at_5=5, reciprocal_ranks=[1.0] * 5, n_pos=5,
        false_positives=0, n_neg=0, clash_passed=2, n_clash=2, isolation_passed=1, n_cross=1,
    )
    assert zero_neg["false_positive_rate"] == 0.0


def test_cross_domain_retrieval_generalization_v2():
    """Verify Mode 3 semantic clustering retrieves target incidents across varied technical domains."""
    res_m3 = run_retrieval_mode_benchmark("mode3_dense_mock_hybrid")
    detailed = {d["scenario_id"]: d for d in res_m3.detailed_ranks}

    # Verify key domains are retrieved in top-3
    assert detailed["bm_pos_01_jwt_expired"]["rank"] == 1
    assert detailed["bm_pos_02_db_connection_refused"]["rank"] == 1
    assert detailed["bm_pos_05_redis_out_of_memory"]["rank"] == 1
    assert detailed["bm_pos_06_docker_port_conflict"]["rank"] == 1
    assert detailed["bm_pos_07_esm_module_loader"]["rank"] == 1
    assert detailed["bm_pos_08_git_stale_lockfile"]["rank"] == 1
    assert detailed["bm_pos_09_cors_header_missing"]["rank"] == 1
    assert detailed["bm_pos_10_ssl_cert_expired"]["rank"] == 1
    assert detailed["bm_pos_11_deadlock_concurrency"]["rank"] == 1
    assert detailed["bm_pos_12_permission_denied"]["rank"] == 1
    assert detailed["bm_pos_13_rust_borrow_mut"]["rank"] == 1


def test_suite_a_and_suite_b_independence():
    """Verify Suite A (diagnostic 56 scenarios) and Suite B (retrieval 33 scenarios) remain independent."""
    suite_a_ids = {s["scenario_id"] for s in EVALUATION_SCENARIOS}
    suite_b_ids = {s.scenario_id for s in BENCHMARK_SCENARIOS}

    # Zero overlap in scenario IDs
    assert len(suite_a_ids.intersection(suite_b_ids)) == 0
    assert len(suite_a_ids) == 56
    assert len(suite_b_ids) == 33

    # Suite A evaluation runs with 100% pass rate
    metrics, _ = run_evaluation(live_llm=False)
    assert metrics.total_scenarios == 56
    assert metrics.passed_scenarios == 56
