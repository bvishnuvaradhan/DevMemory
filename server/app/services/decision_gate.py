"""LLM Call Decision Gate for DevMemory Incident Diagnosis.

Enforces intelligent, safe decision-making before external LLM dispatch:
1. Exact known error + compatible verified fix -> return verified fix without calling LLM.
2. General knowledge match -> return stored guidance without calling LLM when sufficiently reliable.
3. Similar incident + verified resolution -> reuse verified fix without calling LLM when evidence is sufficient.
4. New or unfamiliar error -> call LLM when evidence is insufficient.
5. Ambiguous error -> call LLM only when further analysis is useful and sanitized context exists.
6. Explicit fresh-analysis request -> bypass normal reuse and call LLM when authorized.
7. Redaction/security failure -> never dispatch external LLM request (zero provider calls).

Guarantees:
- Never treat similarity alone or unverified fixes as proof that a solution is safe.
- Unverified/failed fixes are NEVER returned as verified.
- Project isolation and cross-project privacy restrictions are strictly preserved.
- Records clear decision reasons for audit and observability.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import ai_engine.schemas as ai_schemas
from ai_engine.diagnosis import _synthesize_fallback_diagnosis
from ai_engine.privacy import redact_secrets, sanitize_file_path
from ai_engine.retrieval import AuthorizationContext, RetrievalResult
from ai_engine.schemas import FixStatus, FixVerificationStatus, IncidentMatch, MatchSource
from app.services.llm_audit_service import validate_outbound_safety

logger = logging.getLogger(__name__)

# Minimum similarity score for an exact error match
EXACT_MATCH_THRESHOLD = 0.95
# Minimum similarity score for a similar incident with verified fix
SIMILAR_VERIFIED_THRESHOLD = 0.70
# Minimum similarity score for reliable curated general knowledge guidance
GENERAL_KNOWLEDGE_THRESHOLD = 0.70


class DecisionReason(str, Enum):
    """Auditable reasons for decision gate routing."""
    EXACT_VERIFIED_FIX = "exact_error_compatible_verified_fix"
    SIMILAR_VERIFIED_RESOLUTION = "similar_incident_verified_resolution"
    GENERAL_KNOWLEDGE_MATCH = "general_knowledge_guidance_match"
    FRESH_ANALYSIS_REQUESTED = "explicit_fresh_analysis_requested"
    INSUFFICIENT_EVIDENCE = "insufficient_retrieval_evidence"
    UNVERIFIED_FIX_NEEDS_ANALYSIS = "unverified_fix_requires_llm_analysis"
    AMBIGUOUS_ERROR_NEEDS_ANALYSIS = "ambiguous_error_requires_llm_analysis"
    REDACTION_SECURITY_FAILURE = "redaction_security_failure"
    EXTERNAL_INFERENCE_DISABLED = "external_inference_disabled_by_policy"


@dataclass
class DecisionGateEvaluation:
    """Outcome of the decision gate evaluation."""
    should_call_llm: bool
    decision_reason: str
    reused_match: Optional[IncidentMatch] = None
    synthesized_response: Optional[ai_schemas.DiagnosisResponse] = None
    is_verified_fix: bool = False


def _build_verified_fix_response(
    request: ai_schemas.DiagnosisRequest,
    match: IncidentMatch,
    all_matches: List[IncidentMatch],
    is_exact: bool = False,
    decision_reason: str = DecisionReason.EXACT_VERIFIED_FIX.value,
) -> ai_schemas.DiagnosisResponse:
    """Synthesize structured DiagnosisResponse from an authorized verified precedent fix."""
    safe_cmd = sanitize_file_path(redact_secrets(request.command))
    safe_err = sanitize_file_path(redact_secrets(request.error_message))
    resolution = match.resolution_summary or "Apply verified resolution steps from precedent incident."

    summary = (
        f"Exact verified fix reused from precedent {match.incident_id}"
        if is_exact
        else f"Verified resolution reused from similar precedent {match.incident_id}"
    )
    likely_cause = f"Precedent in {match.match_source.value} ({match.similarity_score:.0%}): {match.explanation}"

    evidence = [
        f"Executed command: {safe_cmd} (exit code {request.exit_code})",
        f"Observed error: {safe_err}",
        f"Precedent incident: {match.incident_id} (similarity: {match.similarity_score:.0%}, verification: verified)",
    ]
    if request.locations:
        loc = request.locations[0]
        evidence.append(f"Failing location: {sanitize_file_path(loc.file_path)}:{loc.line}")

    hypotheses = [
        f"Verified root cause matching {match.incident_id}: {match.explanation}",
        "Precedent fix verified in prior execution",
    ]

    steps = [s.strip() for s in re.split(r";\s*|\n+", resolution) if s.strip()]
    if not steps:
        steps = [resolution]

    confidence = min(1.0, max(match.similarity_score, 0.95) if is_exact else max(match.similarity_score, 0.85))

    return ai_schemas.DiagnosisResponse(
        event_id=request.event_id,
        summary=summary,
        likely_cause=likely_cause,
        evidence=evidence,
        hypotheses=hypotheses,
        recommended_steps=steps,
        related_incidents=all_matches[:20],
        uncertainty_description=f"Verified fix reused directly by DevMemory decision gate without external LLM call ({decision_reason}).",
        confidence=confidence,
        verification_steps=[f"Re-run '{safe_cmd}' to verify resolution"],
        fix_status=FixStatus.VERIFIED,
    )


def _build_general_knowledge_response(
    request: ai_schemas.DiagnosisRequest,
    match: IncidentMatch,
    all_matches: List[IncidentMatch],
    decision_reason: str = DecisionReason.GENERAL_KNOWLEDGE_MATCH.value,
) -> ai_schemas.DiagnosisResponse:
    """Synthesize structured DiagnosisResponse from trusted curated knowledge base guidance."""
    safe_cmd = sanitize_file_path(redact_secrets(request.command))
    safe_err = sanitize_file_path(redact_secrets(request.error_message))

    title = match.explanation.split(":")[0] if ":" in match.explanation else match.incident_id
    summary = f"Identified standard issue matching curated knowledge: {title}"
    likely_cause = f"Curated knowledge match ({match.similarity_score:.0%}): {match.explanation}"

    evidence = [
        f"Executed command: {safe_cmd} (exit code {request.exit_code})",
        f"Observed error: {safe_err}",
        f"Knowledge base entry: {match.incident_id} (similarity: {match.similarity_score:.0%})",
    ]
    if request.locations:
        loc = request.locations[0]
        evidence.append(f"Failing location: {sanitize_file_path(loc.file_path)}:{loc.line}")

    hypotheses = [
        f"Standard failure pattern: {match.explanation}",
    ]

    raw_resolutions = match.resolution_summary or ""
    if raw_resolutions.startswith("Suggested resolutions:"):
        raw_resolutions = raw_resolutions[len("Suggested resolutions:"):].strip()

    steps = [s.strip() for s in re.split(r";\s*|\n+", raw_resolutions) if s.strip()]
    if not steps:
        steps = ["Review error logs and apply standard language-specific resolution"]

    return ai_schemas.DiagnosisResponse(
        event_id=request.event_id,
        summary=summary,
        likely_cause=likely_cause,
        evidence=evidence,
        hypotheses=hypotheses,
        recommended_steps=steps,
        related_incidents=all_matches[:20],
        uncertainty_description=f"Stored general knowledge guidance reused directly by DevMemory decision gate without external LLM call ({decision_reason}).",
        confidence=min(1.0, max(match.similarity_score, 0.85)),
        verification_steps=[f"Re-run '{safe_cmd}' after applying standard guidance"],
        fix_status=FixStatus.UNVERIFIED,
    )


def evaluate_decision_gate(
    request: ai_schemas.DiagnosisRequest,
    auth_context: AuthorizationContext,
    retrieval_result: RetrievalResult,
    fresh_analysis: bool = False,
    disable_external_inference: bool = False,
) -> DecisionGateEvaluation:
    """Evaluate whether an error diagnosis requires external LLM inference.

    Flow:
    1. Pre-flight Security / Redaction Verification:
       Never dispatch external LLM when sensitive credentials or policy violations are detected.
    2. Policy Opt-Out / Offline Mode:
       Synthesize deterministic local fallback without provider invocation.
    3. Explicit Fresh-Analysis Request:
       Bypass normal reuse and call LLM when authorized.
    4. Exact Known Error + Compatible Verified Fix:
       Reuse proven fix when exact signature/message matches with verified status.
    5. Similar Incident + Verified Resolution:
       Reuse proven fix when sufficient similarity exists with verified status.
    6. General Knowledge Match:
       Reuse trusted curated guidance when reliability threshold is met.
    7. Unverified / Failed Fix Guard:
       Never treat unverified or failed fixes as proven solutions; call LLM for fresh analysis.
    8. New or Ambiguous Error:
       Call LLM when evidence is insufficient or ambiguous.
    """
    # 1. Redaction / Security Failure Check
    combined_payload_text = f"{request.command}\n{request.error_message}\n{request.stack_trace or ''}"
    is_safe, violation = validate_outbound_safety(
        system_prompt="",
        user_prompt=combined_payload_text,
    )
    if not is_safe:
        logger.warning(
            "Decision Gate: Redaction/security verification failed (%s). External LLM will not be dispatched.",
            violation,
        )
        fallback = _synthesize_fallback_diagnosis(
            request=request,
            retrieval_result=retrieval_result,
            reason=f"Security verification blocked outbound transmission: {violation}",
        )
        return DecisionGateEvaluation(
            should_call_llm=False,
            decision_reason=DecisionReason.REDACTION_SECURITY_FAILURE.value,
            synthesized_response=fallback,
            is_verified_fix=False,
        )

    # 2. External AI Privacy Opt-Out / Offline Enforcement
    if disable_external_inference:
        logger.info("Decision Gate: External AI inference disabled by privacy configuration.")
        fallback = _synthesize_fallback_diagnosis(
            request=request,
            retrieval_result=retrieval_result,
            reason="External AI inference disabled by privacy configuration",
        )
        return DecisionGateEvaluation(
            should_call_llm=False,
            decision_reason=DecisionReason.EXTERNAL_INFERENCE_DISABLED.value,
            synthesized_response=fallback,
            is_verified_fix=False,
        )

    # 3. Explicit Fresh-Analysis Request (Bypass reuse when requested)
    if fresh_analysis:
        logger.info("Decision Gate: Explicit fresh-analysis requested; bypassing memory reuse.")
        return DecisionGateEvaluation(
            should_call_llm=True,
            decision_reason=DecisionReason.FRESH_ANALYSIS_REQUESTED.value,
            is_verified_fix=False,
        )

    # Filter verified precedent fixes strictly (strict unverified fix guarantee)
    verified_matches = [
        m for m in retrieval_result.all_ranked_matches
        if m.match_source in (MatchSource.PROJECT_MEMORY, MatchSource.CROSS_PROJECT)
        and m.verification_status == FixVerificationStatus.VERIFIED
        and bool(m.resolution_summary and m.resolution_summary.strip())
    ]

    # Filter reliable general knowledge matches
    reliable_gk_matches = [
        m for m in retrieval_result.general_matches
        if m.match_source == MatchSource.GENERAL_KNOWLEDGE
        and m.similarity_score >= GENERAL_KNOWLEDGE_THRESHOLD
        and bool(m.resolution_summary or m.explanation)
    ]

    # 4. Exact Known Error + Compatible Verified Fix
    for vm in verified_matches:
        is_exact = (
            vm.similarity_score >= EXACT_MATCH_THRESHOLD
            or "Exact error signature match" in vm.explanation
        )
        if is_exact:
            logger.info(
                "Decision Gate: Exact error matched verified fix from precedent '%s' (similarity: %.2f). Zero LLM calls.",
                vm.incident_id,
                vm.similarity_score,
            )
            resp = _build_verified_fix_response(
                request=request,
                match=vm,
                all_matches=retrieval_result.all_ranked_matches,
                is_exact=True,
                decision_reason=DecisionReason.EXACT_VERIFIED_FIX.value,
            )
            return DecisionGateEvaluation(
                should_call_llm=False,
                decision_reason=DecisionReason.EXACT_VERIFIED_FIX.value,
                reused_match=vm,
                synthesized_response=resp,
                is_verified_fix=True,
            )

    # Evaluate best candidate between Similar Verified Fix vs General Knowledge
    best_similar_verified: Optional[IncidentMatch] = None
    for vm in verified_matches:
        if vm.similarity_score >= SIMILAR_VERIFIED_THRESHOLD:
            best_similar_verified = vm
            break

    best_gk: Optional[IncidentMatch] = reliable_gk_matches[0] if reliable_gk_matches else None

    # 5. Similar Incident + Verified Resolution
    # If a similar verified incident exists and is at least as relevant as general knowledge
    if best_similar_verified and (not best_gk or best_similar_verified.similarity_score >= best_gk.similarity_score):
        logger.info(
            "Decision Gate: Similar incident matched verified fix from precedent '%s' (similarity: %.2f). Zero LLM calls.",
            best_similar_verified.incident_id,
            best_similar_verified.similarity_score,
        )
        resp = _build_verified_fix_response(
            request=request,
            match=best_similar_verified,
            all_matches=retrieval_result.all_ranked_matches,
            is_exact=False,
            decision_reason=DecisionReason.SIMILAR_VERIFIED_RESOLUTION.value,
        )
        return DecisionGateEvaluation(
            should_call_llm=False,
            decision_reason=DecisionReason.SIMILAR_VERIFIED_RESOLUTION.value,
            reused_match=best_similar_verified,
            synthesized_response=resp,
            is_verified_fix=True,
        )

    # 6. General Knowledge Match
    if best_gk:
        logger.info(
            "Decision Gate: General knowledge matched curated entry '%s' (similarity: %.2f). Zero LLM calls.",
            best_gk.incident_id,
            best_gk.similarity_score,
        )
        resp = _build_general_knowledge_response(
            request=request,
            match=best_gk,
            all_matches=retrieval_result.all_ranked_matches,
            decision_reason=DecisionReason.GENERAL_KNOWLEDGE_MATCH.value,
        )
        return DecisionGateEvaluation(
            should_call_llm=False,
            decision_reason=DecisionReason.GENERAL_KNOWLEDGE_MATCH.value,
            reused_match=best_gk,
            synthesized_response=resp,
            is_verified_fix=False,
        )

    # 7. Unverified or Failed Fix Guard:
    # If top match exists but fix is unverified or failed, similarity alone is insufficient.
    # We must never treat unverified fixes as proven resolutions -> dispatch to LLM for fresh analysis.
    unverified_precedents = [
        m for m in retrieval_result.all_ranked_matches
        if m.match_source in (MatchSource.PROJECT_MEMORY, MatchSource.CROSS_PROJECT)
        and m.verification_status != FixVerificationStatus.VERIFIED
    ]
    if unverified_precedents:
        top_unverified = unverified_precedents[0]
        if top_unverified.similarity_score >= SIMILAR_VERIFIED_THRESHOLD:
            logger.info(
                "Decision Gate: Precedent '%s' matched with similarity %.2f, but fix status is '%s' (unverified). Calling LLM.",
                top_unverified.incident_id,
                top_unverified.similarity_score,
                top_unverified.verification_status.value,
            )
            return DecisionGateEvaluation(
                should_call_llm=True,
                decision_reason=DecisionReason.UNVERIFIED_FIX_NEEDS_ANALYSIS.value,
                is_verified_fix=False,
            )

    # 8. Ambiguous or Unfamiliar Error:
    # If matches exist but have marginal similarity (below threshold), error is ambiguous.
    if retrieval_result.all_ranked_matches and retrieval_result.all_ranked_matches[0].similarity_score >= 0.40:
        logger.info("Decision Gate: Matches are ambiguous (low confidence). Calling LLM for thorough analysis.")
        return DecisionGateEvaluation(
            should_call_llm=True,
            decision_reason=DecisionReason.AMBIGUOUS_ERROR_NEEDS_ANALYSIS.value,
            is_verified_fix=False,
        )

    # 9. New or Unfamiliar Error (Insufficient Evidence)
    logger.info("Decision Gate: New or unfamiliar error with insufficient retrieval evidence. Calling LLM.")
    return DecisionGateEvaluation(
        should_call_llm=True,
        decision_reason=DecisionReason.INSUFFICIENT_EVIDENCE.value,
        is_verified_fix=False,
    )
