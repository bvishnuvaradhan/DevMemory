"""AI Service Adapter Layer bridging Backend and Member 3's AI Engine.

Implements:
1. MongoIncidentRepository - fulfills IncidentRepository protocol against MongoDB collections.
2. build_ai_diagnosis_payloads - maps stored backend incidents to DiagnosisRequest and AuthorizationContext.
3. map_ai_response_to_backend_diagnosis - converts ai_engine.schemas.DiagnosisResponse to DiagnosisCreate.
4. map_ai_response_to_cli_diagnosis_dict - formats ai_engine.schemas.DiagnosisResponse for CLI consumption.
5. generate_and_store_incident_diagnosis - orchestrates full diagnostic execution and persists results.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from pymongo.database import Database

import ai_engine.schemas as ai_schemas
from ai_engine.diagnosis import diagnose_error
from ai_engine.retrieval import AuthorizationContext, IncidentRepository
from app.config import get_settings
from app.schemas.diagnosis import (
    DiagnosisCreate,
    DiagnosisResponse as BackendDiagnosisResponseModel,
    HypothesisItem,
    MatchedMemoryRef,
)
from app.services import diagnosis_service

logger = logging.getLogger(__name__)


class MongoIncidentRepository:
    """Adapter implementing ai_engine.retrieval.IncidentRepository against MongoDB collections."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _enrich_incident(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and enrich stored incident document for AI engine consumption."""
        enriched = dict(doc)
        if "_id" in enriched:
            enriched.pop("_id", None)

        inc_id = enriched.get("incident_id", "")
        event_id = enriched.get("event_id")

        # Enrich command and stack_trace from command_runs if missing
        if event_id and (not enriched.get("command") or not enriched.get("stack_trace")):
            run_doc = self.db.command_runs.find_one(
                {"event_id": event_id},
                {"_id": 0, "command": 1, "stderr": 1},
            )
            if run_doc:
                if not enriched.get("command"):
                    enriched["command"] = run_doc.get("command", "")
                if not enriched.get("stack_trace"):
                    enriched["stack_trace"] = run_doc.get("stderr", "")

        # Enrich fix outcome and verification status if present
        if not enriched.get("verification_status") or enriched.get("verification_status") == "unverified":
            fix = self.db.fix_outcomes.find_one(
                {"incident_id": inc_id},
                sort=[("created_at", -1)],
            )
            if fix:
                fix_stat = fix.get("status")
                if fix_stat == "verified":
                    enriched["verification_status"] = "verified"
                elif fix_stat in ("failed", "reverted"):
                    enriched["verification_status"] = "failed"
                else:
                    enriched["verification_status"] = "unverified"
                if not enriched.get("resolution_summary"):
                    enriched["resolution_summary"] = fix.get("description")
            else:
                enriched["verification_status"] = "unverified"

        enriched["is_public"] = bool(enriched.get("is_public", False))
        enriched["disclose_project_id"] = bool(enriched.get("disclose_project_id", False))
        return enriched

    def get_project_incidents(self, project_id: str) -> List[Dict[str, Any]]:
        """Retrieve stored historical incidents for a specific project."""
        cursor = self.db.incidents.find({"project_id": project_id}, {"_id": 0})
        return [self._enrich_incident(doc) for doc in cursor]

    def get_cross_project_incidents(self, requesting_project_id: str) -> List[Dict[str, Any]]:
        """Retrieve cross-project incident candidates strictly filtered by is_public=True."""
        cursor = self.db.incidents.find(
            {"project_id": {"$ne": requesting_project_id}, "is_public": True},
            {"_id": 0},
        )
        return [self._enrich_incident(doc) for doc in cursor]


def build_ai_diagnosis_payloads(
    incident: Dict[str, Any],
    run: Optional[Dict[str, Any]] = None,
    allow_cross_project: bool = True,
    has_cross_project_read: bool = False,
    user_id: str = "system",
) -> Tuple[ai_schemas.DiagnosisRequest, AuthorizationContext]:
    """Construct validated DiagnosisRequest and AuthorizationContext from stored records."""
    event_id = incident.get("event_id") or f"evt_{incident.get('incident_id', 'unknown')}"
    project_id = incident["project_id"]

    command = ""
    if run and run.get("command"):
        command = run["command"]
    elif incident.get("command"):
        command = incident["command"]
    if not command:
        command = "command"
    command = str(command)[:2000]

    exit_code = 1
    if run and run.get("exit_code") is not None:
        exit_code = int(run["exit_code"])
    elif incident.get("exit_code") is not None:
        exit_code = int(incident["exit_code"])

    error_message = incident.get("error_message") or (run.get("stderr") if run else "") or "Unknown command failure"
    error_message = str(error_message)[:10000]

    stack_trace = None
    if run and run.get("stderr"):
        stack_trace = str(run["stderr"])[:50000]
    elif incident.get("stack_trace"):
        stack_trace = str(incident["stack_trace"])[:50000]

    locations: List[ai_schemas.SourceLocation] = []
    file_path = incident.get("file_path")
    line = incident.get("line")
    col = incident.get("column")
    if file_path and line and int(line) > 0:
        locations.append(
            ai_schemas.SourceLocation(
                file_path=str(file_path)[:1000],
                line=int(line),
                column=int(col) if col and int(col) > 0 else None,
            )
        )

    source_snippets: List[ai_schemas.SourceSnippet] = []
    snippet_content = incident.get("source_snippet")
    if file_path and snippet_content:
        s_line = max(1, (int(line) if line and int(line) > 0 else 1) - 2)
        line_count = len(snippet_content.splitlines())
        e_line = s_line + max(0, line_count - 1)
        source_snippets.append(
            ai_schemas.SourceSnippet(
                file_path=str(file_path)[:1000],
                start_line=s_line,
                end_line=e_line,
                content=str(snippet_content)[:20000],
            )
        )

    req = ai_schemas.DiagnosisRequest(
        event_id=event_id,
        project_id=project_id,
        command=command,
        exit_code=exit_code,
        error_message=error_message,
        stack_trace=stack_trace,
        locations=locations,
        source_snippets=source_snippets,
        allow_cross_project=bool(allow_cross_project),
    )

    auth = AuthorizationContext(
        user_id=user_id,
        project_id=project_id,
        has_project_access=True,
        has_cross_project_read=bool(has_cross_project_read),
    )

    return req, auth


def map_ai_response_to_backend_diagnosis(
    ai_resp: ai_schemas.DiagnosisResponse,
    incident_id: str,
) -> DiagnosisCreate:
    """Map ai_engine DiagnosisResponse to backend's DiagnosisCreate persistence model."""
    hypotheses = [
        HypothesisItem(
            cause=h[:1000],
            is_observed=False,
            details=None,
        )
        for h in ai_resp.hypotheses
    ]

    matched_memory = [
        MatchedMemoryRef(
            source_id=m.incident_id[:128],
            source_type=m.match_source.value,
            relevance_reason=m.explanation[:1000] if m.explanation else None,
        )
        for m in ai_resp.related_incidents
    ]

    suggested_fix = "; ".join(ai_resp.recommended_steps) if ai_resp.recommended_steps else None
    if suggested_fix and len(suggested_fix) > 5000:
        suggested_fix = suggested_fix[:5000]

    return DiagnosisCreate(
        summary=ai_resp.summary[:2000],
        hypotheses=hypotheses,
        suggested_fix=suggested_fix,
        matched_memory=matched_memory,
        evidence=ai_resp.evidence[:100],
        confidence=ai_resp.confidence,
        source="ai_engine/groq-llama-3.3-70b",
    )


def map_ai_response_to_cli_diagnosis_dict(
    ai_resp: ai_schemas.DiagnosisResponse,
    incident_id: str,
    event_id: str,
) -> Dict[str, Any]:
    """Format AI diagnosis into CLI-compatible response structure."""
    similar_incidents = []
    for m in ai_resp.related_incidents:
        similar_incidents.append({
            "incident_id": m.incident_id,
            "project_name": m.project_id or ("Curated Knowledge" if m.match_source == ai_schemas.MatchSource.GENERAL_KNOWLEDGE else "cross-project"),
            "similarity_score": m.similarity_score,
            "summary": m.explanation or m.resolution_summary or "",
            "verified_fix": m.resolution_summary if m.verification_status == ai_schemas.FixVerificationStatus.VERIFIED else None,
            "is_cross_project": (m.match_source == ai_schemas.MatchSource.CROSS_PROJECT),
        })

    return {
        "status": "success",
        "event_id": event_id,
        "incident_id": incident_id,
        "probable_cause": ai_resp.likely_cause,
        "hypotheses": ai_resp.hypotheses,
        "suggested_steps": ai_resp.recommended_steps,
        "similar_incidents": similar_incidents,
        "raw_response": ai_resp.model_dump(),
        "is_verified_fix": False,  # Strict Unverified Fix Guarantee
    }


def generate_and_store_incident_diagnosis(
    db: Database,
    incident_id: str,
    allow_cross_project: bool = True,
    has_cross_project_read: bool = False,
    disable_external_inference: Optional[bool] = None,
    threshold: float = 0.60,
) -> Tuple[BackendDiagnosisResponseModel, bool]:
    """Execute AI diagnosis for an incident and persist the structured diagnosis in MongoDB."""
    incident = db.incidents.find_one({"incident_id": incident_id}, {"_id": 0})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    run = None
    event_id = incident.get("event_id")
    if event_id:
        run = db.command_runs.find_one({"event_id": event_id}, {"_id": 0})

    req, auth = build_ai_diagnosis_payloads(
        incident=incident,
        run=run,
        allow_cross_project=allow_cross_project,
        has_cross_project_read=has_cross_project_read,
    )

    repo = MongoIncidentRepository(db)

    # Run AI diagnosis orchestrator
    ai_resp = diagnose_error(
        request=req,
        auth_context=auth,
        repository=repo,
        threshold=threshold,
        disable_external_inference=disable_external_inference,
    )

    # Map AI response to backend diagnosis schema
    backend_payload = map_ai_response_to_backend_diagnosis(ai_resp, incident_id)

    # Persist via diagnosis service (which handles idempotency, updates status, etc.)
    diagnosis_resp, is_new = diagnosis_service.create_diagnosis(
        db=db,
        incident_id=incident_id,
        payload=backend_payload,
    )

    return diagnosis_resp, is_new


def check_groq_provider_readiness() -> Dict[str, Any]:
    """Check Groq provider readiness and configuration status safely without leaking secrets.

    Returns:
        Dict containing status, is_configured, model, timeout_seconds, and masked_key.
    """
    settings = get_settings()
    api_key = os.getenv("GROQ_API_KEY") or settings.GROQ_API_KEY
    is_offline = (
        os.getenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "").lower() in ("1", "true", "yes")
        or os.getenv("DEVMEMORY_OFFLINE_MODE", "").lower() in ("1", "true", "yes")
        or os.getenv("AI_PRIVACY_OFFLINE_ONLY", "").lower() in ("1", "true", "yes")
        or (settings.DEV_MEMORY_DISABLE_EXTERNAL_AI or "").lower() in ("1", "true", "yes")
    )

    if is_offline:
        return {
            "status": "offline_mode_enforced",
            "is_configured": bool(api_key),
            "model": os.getenv("GROQ_MODEL", settings.GROQ_MODEL),
            "message": "External AI inference is disabled by privacy configuration (offline mode).",
        }

    if not api_key:
        return {
            "status": "unconfigured",
            "is_configured": False,
            "model": os.getenv("GROQ_MODEL", settings.GROQ_MODEL),
            "message": "GROQ_API_KEY is not configured. Safe deterministic fallback will be used.",
        }

    # Mask key safely: display prefix and length bounds only, never full secret
    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
    return {
        "status": "configured",
        "is_configured": True,
        "model": os.getenv("GROQ_MODEL", settings.GROQ_MODEL),
        "timeout_seconds": float(os.getenv("GROQ_TIMEOUT_SECONDS", str(settings.GROQ_TIMEOUT_SECONDS))),
        "masked_key": masked_key,
        "message": "Groq API credentials are configured and ready for live requests.",
    }


def validate_live_groq_connection() -> Dict[str, Any]:
    """Perform a minimal live Groq connectivity check if configured, without leaking secrets."""
    status_info = check_groq_provider_readiness()
    if not status_info["is_configured"]:
        return {
            "success": False,
            "status": "unconfigured",
            "message": "GROQ_API_KEY is not configured; live validation was not performed.",
        }

    if status_info["status"] == "offline_mode_enforced":
        return {
            "success": False,
            "status": "offline_mode_enforced",
            "message": "Offline mode is enforced; live validation was skipped.",
        }

    try:
        from ai_engine.llm_client import GroqLLMClient

        client = GroqLLMClient()
        response = client.generate_diagnosis(
            system_prompt="You are a diagnostic assistant. Respond in valid JSON with key 'status'.",
            user_prompt="ping",
        )
        return {
            "success": True,
            "status": "connected",
            "model": client.model,
            "message": "Live Groq connectivity validated successfully.",
        }
    except Exception as exc:
        from ai_engine.privacy import redact_secrets

        sanitized_err = redact_secrets(str(exc))
        return {
            "success": False,
            "status": "error",
            "message": f"Live Groq request failed: {sanitized_err}",
        }
