"""Quality metrics calculation with explicit definitions and denominators for DevMemory."""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class EvaluationMetrics:
    """Rigorous evaluation metrics with explicit denominators."""

    # Level 1 Retrieval Metrics
    retrieval_recall_at_3: float  # Top-3 contains expected KB / cases with expected KB
    retrieval_precision_at_1: float  # Top-1 is expected KB / cases with expected KB
    false_positive_rate: float  # Surfaced match above threshold / cases with no expected match

    # Level 2 & 3 Scoping & Authorization
    project_scoping_accuracy: float  # Zero leak of external project in Level 2 / scoped cases
    cross_project_auth_accuracy: float  # Strict adherence to server authorization / cross-project cases

    # Security & Integrity
    secret_redaction_rate: float  # All synthetic secrets redacted / cases with secrets
    unverified_status_compliance: float  # fix_status is unverified / all cases
    event_id_preservation_rate: float  # event_id strictly preserved / all cases

    # Diagnosis Quality & Grounding
    root_cause_accuracy: float  # Diagnosed cause aligns with expected category / scorable cases
    evidence_grounding_rate: float  # Evidence contains relevant error tokens / cases with tokens
    unsupported_claim_rate: float  # False verification or hallucinated claims / all cases
    insufficient_evidence_handling_rate: float  # Acknowledges uncertainty / insufficient cases
    fallback_resilience_rate: float  # Successful fallback on provider failure / provider failure cases

    # Scenario Counts
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    unscorable_scenarios: int

    # Failure Pattern Breakdown (Task 5)
    failure_pattern_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_scenarios": self.total_scenarios,
            "passed_scenarios": self.passed_scenarios,
            "failed_scenarios": self.failed_scenarios,
            "unscorable_scenarios": self.unscorable_scenarios,
            "pass_rate_percent": round((self.passed_scenarios / self.total_scenarios) * 100, 2)
            if self.total_scenarios > 0
            else 0.0,
            "metrics": {
                "RetrievalRecall@3": {
                    "value": round(self.retrieval_recall_at_3 * 100, 2),
                    "formula": "Hits in top-3 / Scenarios with expected KB target",
                    "definition": "Proportion of scenarios with a target KB item where the target was present in the top-3 ranked results.",
                },
                "RetrievalPrecision@1": {
                    "value": round(self.retrieval_precision_at_1 * 100, 2),
                    "formula": "Top-1 exact hits / Scenarios with expected KB target",
                    "definition": "Proportion of scenarios with a target KB item where the top-ranked result matched the target.",
                },
                "FalsePositiveRate": {
                    "value": round(self.false_positive_rate * 100, 2),
                    "formula": "Non-target queries scoring >= 0.70 / Non-target scenarios",
                    "definition": "Proportion of scenarios without a valid error target where unrelated items scored >= threshold.",
                },
                "ProjectScopingAccuracy": {
                    "value": round(self.project_scoping_accuracy * 100, 2),
                    "formula": "Zero cross-project leaks into Level 2 / Total project queries",
                    "definition": "Proportion of project queries where incidents from other projects were completely excluded from Level 2 memory.",
                },
                "CrossProjectAuthAccuracy": {
                    "value": round(self.cross_project_auth_accuracy * 100, 2),
                    "formula": "Compliant auth & sanitization / Authorized cross-project queries",
                    "definition": "Proportion of cross-project queries where server-side authorization and public policy were strictly enforced.",
                },
                "SecretRedactionRate": {
                    "value": round(self.secret_redaction_rate * 100, 2),
                    "formula": "Completely sanitized outputs / Credential-bearing scenarios",
                    "definition": "Proportion of credential-bearing scenarios where all synthetic secrets were redacted before processing.",
                },
                "UnverifiedStatusCompliance": {
                    "value": round(self.unverified_status_compliance * 100, 2),
                    "formula": "Preserved 'unverified' status / Total diagnosed scenarios",
                    "definition": "Proportion of diagnosed scenarios where fix_status was correctly set to unverified (preventing premature verification claims).",
                },
                "EventIdPreservationRate": {
                    "value": round(self.event_id_preservation_rate * 100, 2),
                    "formula": "Output event_id strictly equal to input / Total scenarios",
                    "definition": "Proportion of diagnosed scenarios where output event_id strictly matches originating request event_id.",
                },
                "RootCauseAccuracy": {
                    "value": round(self.root_cause_accuracy * 100, 2),
                    "formula": "Diagnosed category in expected categories / Scorable scenarios",
                    "definition": "Proportion of scorable scenarios where diagnosis correctly identified an acceptable root cause category.",
                },
                "EvidenceGroundingRate": {
                    "value": round(self.evidence_grounding_rate * 100, 2),
                    "formula": "Retained >=50% key tokens in diagnosis evidence / Scenarios with evidence tokens",
                    "definition": "Proportion of scenarios where diagnosis evidence retained essential diagnostic tokens from the input.",
                },
                "UnsupportedClaimRate": {
                    "value": round(self.unsupported_claim_rate * 100, 2),
                    "formula": "Hallucinated verifications or ungrounded claims / Total scenarios",
                    "definition": "Proportion of scenarios where unverified solutions were prematurely marked verified or ungrounded locations were hallucinated.",
                },
                "InsufficientEvidenceHandlingRate": {
                    "value": round(self.insufficient_evidence_handling_rate * 100, 2),
                    "formula": "Explicitly acknowledged uncertainty / Insufficient evidence scenarios",
                    "definition": "Proportion of scenarios with truncated or vague errors where uncertainty was explicitly acknowledged.",
                },
                "FallbackResilienceRate": {
                    "value": round(self.fallback_resilience_rate * 100, 2),
                    "formula": "Successful deterministic fallback executions / Provider failure scenarios",
                    "definition": "Proportion of simulated provider failure scenarios (timeouts, malformed JSON) where deterministic fallback succeeded.",
                },
            },
            "failure_pattern_breakdown": self.failure_pattern_counts,
        }
