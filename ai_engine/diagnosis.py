"""Diagnosis orchestrator for DevMemory AI & Memory Engine.

Coordinates:
1. Input validation and privacy sanitization.
2. Three-level memory retrieval.
3. Outbound payload safety validation and minimization.
4. Structured LLM diagnosis generation.
5. Privacy opt-out / offline fallback configuration.
6. Fallback synthesis on provider timeout, failure, or policy blocks.
7. Post-processing sanitization on LLM responses to prevent echoed secrets.
"""

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from ai_engine.llm_client import GroqLLMClient, LLMClient, MockLLMClient
from ai_engine.privacy import (
    redact_secrets,
    sanitize_diagnosis_request,
    sanitize_file_path,
    validate_outbound_payload_safety,
)
from ai_engine.prompts import build_diagnosis_prompt
from ai_engine.retrieval import (
    AuthorizationContext,
    IncidentRepository,
    RetrievalResult,
    retrieve_memory,
)
from ai_engine.schemas import (
    DiagnosisRequest,
    DiagnosisResponse,
    FixStatus,
    IncidentMatch,
    MatchSource,
)

logger = logging.getLogger(__name__)


def _clean_json_text(raw_text: str) -> str:
    """Strip markdown code fence wrappers (e.g. ```json ... ```) if present."""
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _synthesize_fallback_diagnosis(
    request: DiagnosisRequest,
    retrieval_result: RetrievalResult,
    reason: str,
) -> DiagnosisResponse:
    """Generate a deterministic fallback diagnosis when external LLM is disabled, fails, or is blocked.
    
    Synthesizes actionable guidance directly from Level 1 curated knowledge
    and retrieved historical incidents without crashing the application.
    All synthesized fields are strictly sanitized.
    """
    safe_cmd = sanitize_file_path(redact_secrets(request.command))
    safe_err = sanitize_file_path(redact_secrets(request.error_message))

    evidence = [
        f"Executed command: {safe_cmd} (exit code {request.exit_code})",
        f"Observed error: {safe_err}",
    ]
    if request.locations:
        loc = request.locations[0]
        safe_loc_path = sanitize_file_path(loc.file_path)
        evidence.append(f"Failing location: {safe_loc_path}:{loc.line}")

    hypotheses = ["Runtime execution failure"]
    recommended_steps = ["Review error logs and recent codebase modifications"]
    summary = f"Failure during execution of '{safe_cmd}'"
    likely_cause = f"The command terminated with code {request.exit_code}: {safe_err}"

    # Use best available match from 3-level retrieval
    if retrieval_result.all_ranked_matches:
        top_match = retrieval_result.all_ranked_matches[0]
        summary = f"Identified probable cause matching {top_match.incident_id}"
        likely_cause = f"Matched {top_match.match_source.value} ({top_match.similarity_score:.0%}): {top_match.explanation}"
        hypotheses = [
            f"Precedent hypothesis from {top_match.incident_id}: {top_match.explanation}",
            "Underlying dependency, configuration, or environment mismatch",
        ]
        if top_match.resolution_summary:
            recommended_steps.insert(0, f"Consider precedent resolution: {top_match.resolution_summary}")
            hypotheses.append(top_match.resolution_summary)

    safe_reason = redact_secrets(reason)

    return DiagnosisResponse(
        event_id=request.event_id,
        summary=summary,
        likely_cause=likely_cause,
        evidence=evidence,
        hypotheses=hypotheses,
        recommended_steps=recommended_steps,
        related_incidents=retrieval_result.all_ranked_matches,
        uncertainty_description=f"Fallback diagnosis synthesized from local knowledge base ({safe_reason}).",
        confidence=0.70 if retrieval_result.all_ranked_matches else 0.40,
        verification_steps=[f"Re-run '{safe_cmd}' after applying proposed adjustments"],
        fix_status=FixStatus.UNVERIFIED,
    )


def diagnose_error(
    request: DiagnosisRequest,
    auth_context: AuthorizationContext,
    repository: Optional[IncidentRepository] = None,
    llm_client: Optional[LLMClient] = None,
    threshold: float = 0.60,
    disable_external_inference: Optional[bool] = None,
) -> DiagnosisResponse:
    """Diagnose a developer error using 3-level memory retrieval and structured LLM inference.
    
    Flow:
    1. Check privacy configuration: if offline opt-out is enabled, synthesize local fallback.
    2. Query 3-level memory (General Knowledge, Project Memory, Cross-Project Precedents).
    3. Build evidence-grounded, privacy-sanitized prompt.
    4. Validate outbound prompt against privacy safety policies.
    5. Call LLM provider with fallback handling on timeout, failure, or policy violations.
    6. Validate structured response against DiagnosisResponse schema.
    7. Sanitize LLM-returned fields to prevent echoed secret leakage.
    8. Attach related incidents and enforce unverified fix status.
    """
    # 1. Check external AI privacy opt-out
    offline_only = bool(disable_external_inference) or (
        os.getenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "").lower() in ("1", "true", "yes")
        or os.getenv("AI_PRIVACY_OFFLINE_ONLY", "").lower() in ("1", "true", "yes")
    )

    # 2. Memory retrieval
    retrieval_result = retrieve_memory(
        request=request,
        auth_context=auth_context,
        repository=repository,
        threshold=threshold,
    )

    # If external inference is disabled by configuration, return deterministic local fallback immediately
    if offline_only:
        logger.info("External AI inference disabled by privacy configuration; using deterministic fallback.")
        return _synthesize_fallback_diagnosis(
            request,
            retrieval_result,
            reason="External AI inference disabled by privacy configuration",
        )

    # 3. Select client
    active_client = llm_client
    if active_client is None:
        if os.getenv("GROQ_API_KEY"):
            active_client = GroqLLMClient()
        else:
            active_client = MockLLMClient()

    # 4. Construct prompt
    system_prompt, user_prompt = build_diagnosis_prompt(request, retrieval_result)

    # 5. Outbound policy safety validation
    safety_report = validate_outbound_payload_safety(user_prompt)
    if not safety_report["is_safe"]:
        violations_str = ", ".join(safety_report["violations"])
        logger.warning(
            "Outbound payload blocked by privacy safety policy (%s); using deterministic fallback.",
            violations_str,
        )
        return _synthesize_fallback_diagnosis(
            request,
            retrieval_result,
            reason=f"Outbound payload blocked by privacy policy: {violations_str}",
        )

    # 6. Generate diagnosis via LLM with fallback
    try:
        raw_json = active_client.generate_diagnosis(system_prompt, user_prompt)
        cleaned_json = _clean_json_text(raw_json)
        data: Dict[str, Any] = json.loads(cleaned_json)

        # Enforce consistency with request event_id
        data["event_id"] = request.event_id

        # Enforce unverified fix status rule: LLM recommendations cannot be marked verified
        if data.get("fix_status") == FixStatus.VERIFIED.value:
            data["fix_status"] = FixStatus.UNVERIFIED.value

        # Attach retrieved incidents
        data["related_incidents"] = retrieval_result.all_ranked_matches

        # Post-process LLM response fields to sanitize any reflected secrets
        if isinstance(data.get("summary"), str):
            data["summary"] = redact_secrets(sanitize_file_path(data["summary"]))
        if isinstance(data.get("likely_cause"), str):
            data["likely_cause"] = redact_secrets(sanitize_file_path(data["likely_cause"]))
        if isinstance(data.get("hypotheses"), list):
            data["hypotheses"] = [
                redact_secrets(sanitize_file_path(str(h))) for h in data["hypotheses"]
            ]
        if isinstance(data.get("recommended_steps"), list):
            data["recommended_steps"] = [
                redact_secrets(sanitize_file_path(str(s))) for s in data["recommended_steps"]
            ]
        if isinstance(data.get("evidence"), list):
            data["evidence"] = [
                redact_secrets(sanitize_file_path(str(e))) for e in data["evidence"]
            ]

        return DiagnosisResponse.model_validate(data)

    except Exception as exc:
        safe_exc = redact_secrets(str(exc))
        logger.warning("LLM diagnosis generation failed (%s); generating deterministic fallback.", safe_exc)
        return _synthesize_fallback_diagnosis(request, retrieval_result, safe_exc)
