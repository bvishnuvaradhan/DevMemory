"""Tests executing the 50+ scenario evaluation suite and asserting quality benchmarks."""

import json
from pathlib import Path
import pytest

from ai_engine.evaluation import (
    DATASET_VERSION,
    EVALUATION_SCENARIOS,
    export_evaluation_reports,
    run_evaluation,
)
from ai_engine.schemas import DiagnosisRequest


def test_evaluation_dataset_completeness():
    """Verify that the evaluation dataset covers >= 50 scenarios and all required domains."""
    assert len(EVALUATION_SCENARIOS) >= 50
    assert DATASET_VERSION == "2.1.0"

    categories = {scn["category"] for scn in EVALUATION_SCENARIOS}
    required_categories = {
        "python_runtime",
        "js_runtime",
        "network",
        "configuration",
        "testing",
        "dependency",
        "similar_different_cause",
        "insufficient_evidence",
        "unknown_format",
        "misleading_history",
        "privacy_security",
        "provider_failure",
        "build",
        "filesystem",
    }
    for cat in required_categories:
        assert cat in categories, f"Missing category: {cat}"

    # Verify each scenario schema
    for scn in EVALUATION_SCENARIOS:
        assert "scenario_id" in scn
        assert "category" in scn
        assert isinstance(scn["request"], DiagnosisRequest)
        assert "expected_root_cause_categories" in scn
        assert "relevant_evidence_tokens" in scn
        assert "definitive_fix_justified" in scn
        assert isinstance(scn["definitive_fix_justified"], bool)


def test_run_evaluation_quality_benchmarks():
    """Execute full 52-scenario evaluation harness and verify all quality benchmarks pass."""
    metrics, details = run_evaluation(live_llm=False)

    failures = [d for d in details if not d["passed"]]
    if failures:
        fail_msgs = "\n".join(f"{f['scenario_id']}: {f['failures']}" for f in failures)
        pytest.fail(f"Evaluation failures detected ({len(failures)}/{metrics.total_scenarios}):\n{fail_msgs}")

    # Assert rigorous benchmarks
    assert metrics.total_scenarios >= 50
    assert metrics.passed_scenarios == metrics.total_scenarios
    assert metrics.failed_scenarios == 0

    # Retrieval metrics
    assert metrics.retrieval_recall_at_3 == 1.0
    assert metrics.retrieval_precision_at_1 >= 0.90
    assert metrics.false_positive_rate == 0.0

    # Diagnosis quality & Grounding
    assert metrics.root_cause_accuracy >= 0.90
    assert metrics.evidence_grounding_rate >= 0.95
    assert metrics.unsupported_claim_rate == 0.0
    assert metrics.insufficient_evidence_handling_rate == 1.0
    assert metrics.fallback_resilience_rate == 1.0

    # Scoping and security
    assert metrics.project_scoping_accuracy == 1.0
    assert metrics.cross_project_auth_accuracy == 1.0
    assert metrics.secret_redaction_rate == 1.0
    assert metrics.unverified_status_compliance == 1.0
    assert metrics.event_id_preservation_rate == 1.0


def test_export_reports_no_raw_secrets(tmp_path: Path):
    """Verify exported evaluation reports contain no raw API keys or secrets."""
    metrics, details = run_evaluation(live_llm=False)
    json_path, md_path = export_evaluation_reports(metrics, details, output_dir=tmp_path)

    assert json_path.is_file()
    assert md_path.is_file()

    json_text = json_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")

    # Assert sensitive synthetic secrets are not leaked in reports
    forbidden_secrets = [
        "secretKey1234567890abcdef123456",
        "secretSignatureToken123456",
        "SuperSecretP@ssw0rd!",
        "SuperSecretPassword999",
    ]
    for secret in forbidden_secrets:
        assert secret not in json_text
        assert secret not in md_text

    # Assert machine path was sanitized in report
    assert "C:\\Users\\dev\\helper.py" not in json_text
    assert "C:\\Users\\dev\\helper.py" not in md_text


def test_malformed_dataset_scenario_fails_clearly():
    """Verify that an invalid scenario structure fails validation clearly."""
    malformed_scn = [
        {
            "scenario_id": "bad_scenario",
            "category": "invalid",
            # missing request
        }
    ]
    with pytest.raises(KeyError):
        run_evaluation(scenarios=malformed_scn)
