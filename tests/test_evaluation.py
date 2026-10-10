"""Tests executing the 25-scenario evaluation suite and asserting quality benchmarks."""

import pytest

from ai_engine.evaluation import EVALUATION_SCENARIOS, run_evaluation


def test_evaluation_dataset_completeness():
    """Verify that the evaluation dataset covers all required error domains."""
    assert len(EVALUATION_SCENARIOS) >= 25

    categories = {scn["category"] for scn in EVALUATION_SCENARIOS}
    assert "python_runtime" in categories
    assert "js_runtime" in categories
    assert "network" in categories
    assert "configuration" in categories
    assert "testing" in categories
    assert "dependency" in categories
    assert "similar_different_cause" in categories
    assert "insufficient_evidence" in categories
    assert "unknown_format" in categories
    assert "misleading_history" in categories
    assert "privacy_security" in categories


def test_run_evaluation_quality_benchmarks():
    """Execute full evaluation harness and verify all quality benchmarks pass."""
    metrics, details = run_evaluation()

    # Report failure details if any occurred
    failures = [d for d in details if not d["passed"]]
    if failures:
        fail_msgs = "\n".join(f"{f['scenario_id']}: {f['failures']}" for f in failures)
        pytest.fail(f"Evaluation failures detected ({len(failures)}/{metrics.total_scenarios}):\n{fail_msgs}")

    # Assert rigorous benchmarks
    assert metrics.total_scenarios >= 25
    assert metrics.passed_scenarios == metrics.total_scenarios
    assert metrics.failed_scenarios == 0

    # Retrieval metrics
    assert metrics.retrieval_recall_at_3 == 1.0
    assert metrics.retrieval_precision_at_1 >= 0.90
    assert metrics.false_positive_rate == 0.0

    # Scoping and security
    assert metrics.project_scoping_accuracy == 1.0
    assert metrics.cross_project_auth_accuracy == 1.0
    assert metrics.secret_redaction_rate == 1.0
    assert metrics.unverified_status_compliance == 1.0
    assert metrics.event_id_preservation_rate == 1.0
