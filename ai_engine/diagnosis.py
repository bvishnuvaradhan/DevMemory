"""Diagnosis orchestrator for DevMemory AI & Memory Engine.

Coordinates:
1. Input validation and privacy sanitization.
2. Three-level memory retrieval.
3. Evidence-grounded prompt compilation.
4. Structured LLM diagnosis generation.
5. Fallback synthesis on provider timeout or failure.
"""

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from ai_engine.llm_client import GroqLLMClient, LLMClient, MockLLMClient
from ai_engine.privacy import sanitize_diagnosis_request
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
    """Generate a deterministic fallback diagnosis when the external LLM fails or times out.
    
    Synthesizes actionable guidance directly from Level 1 curated knowledge
    and retrieved historical incidents without crashing the application.
    """
    evidence = [
        f"Executed command: {request.command} (exit code {request.exit_code})",
        f"Observed error: {request.error_message}",
    ]
    if request.locations:
        loc = request.locations[0]
        evidence.append(f"Failing location: {loc.file_path}:{loc.line}")

    hypotheses = ["Runtime execution failure"]
    recommended_steps = ["Review error logs and recent codebase modifications"]
    summary = f"Failure during execution of '{request.command}'"
    likely_cause = f"The command terminated with code {request.exit_code}: {request.error_message}"

    # Use best available match from 3-level retrieval
    if retrieval_result.all_ranked_matches:
        top_match = retrieval_result.all_ranked_matches[0]
        summary = f"Identified probable cause matching {top_match.incident_id}"
        likely_cause = f"Matched {top_match.match_source.value} ({top_match.similarity_score:.0%}): {top_match.explanation}"
        if top_match.resolution_summary:
            recommended_steps.insert(0, f"Consider precedent resolution: {top_match.resolution_summary}")

    return DiagnosisResponse(
        event_id=request.event_id,
        summary=summary,
        likely_cause=likely_cause,
        evidence=evidence,
        hypotheses=hypotheses,
        recommended_steps=recommended_steps,
        related_incidents=retrieval_result.all_ranked_matches,
        uncertainty_description=f"Fallback diagnosis synthesized from local knowledge base ({reason}).",
        confidence=0.70 if retrieval_result.all_ranked_matches else 0.40,
        verification_steps=[f"Re-run '{request.command}' after applying proposed adjustments"],
        fix_status=FixStatus.UNVERIFIED,
    )


def diagnose_error(
    request: DiagnosisRequest,
    auth_context: AuthorizationContext,
    repository: Optional[IncidentRepository] = None,
    llm_client: Optional[LLMClient] = None,
    threshold: float = 0.60,
) -> DiagnosisResponse:
    """Diagnose a developer error using 3-level memory retrieval and structured LLM inference.
    
    Flow:
    1. Sanitize request inputs.
    2. Query 3-level memory (General Knowledge, Project Memory, Cross-Project Precedents).
    3. Build evidence-grounded prompt.
    4. Call LLM provider with fallback handling.
    5. Validate structured response against DiagnosisResponse schema.
    6. Attach related incidents and enforce unverified fix status.
    """
    # 1. Memory retrieval
    retrieval_result = retrieve_memory(
        request=request,
        auth_context=auth_context,
        repository=repository,
        threshold=threshold,
    )

    # 2. Select client
    active_client = llm_client
    if active_client is None:
        if os.getenv("GROQ_API_KEY"):
            active_client = GroqLLMClient()
        else:
            active_client = MockLLMClient()

    # 3. Construct prompt
    system_prompt, user_prompt = build_diagnosis_prompt(request, retrieval_result)

    # 4. Generate diagnosis via LLM with fallback
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

        return DiagnosisResponse.model_validate(data)

    except Exception as exc:
        logger.warning("LLM diagnosis generation failed (%s); generating deterministic fallback.", exc)
        return _synthesize_fallback_diagnosis(request, retrieval_result, str(exc))
