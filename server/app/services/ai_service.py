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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.database import Database

import ai_engine.schemas as ai_schemas
from ai_engine.diagnosis import diagnose_error
from ai_engine.retrieval import AuthorizationContext, IncidentRepository, retrieve_memory
from app.config import get_settings
from app.schemas.diagnosis import (
    DiagnosisCreate,
    DiagnosisResponse as BackendDiagnosisResponseModel,
    HypothesisItem,
    MatchedMemoryRef,
)
from app.services import diagnosis_service
from app.services.decision_gate import DecisionReason, evaluate_decision_gate
from app.services.embedding_service import (
    ProductionMongoVectorSearchAdapter,
    get_active_embedding_provider,
)
from app.services.llm_audit_service import AuditedLLMClient, get_audited_llm_client
from app.services.root_cause_analyzer import refine_root_cause_diagnosis

logger = logging.getLogger(__name__)


class MongoIncidentRepository:
    """Adapter implementing ai_engine.retrieval.IncidentRepository against MongoDB collections."""

    def __init__(self, db: Database, current_incident_id: Optional[str] = None) -> None:
        self.db = db
        self.current_incident_id = current_incident_id

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
        verified_fix = self.db.fix_outcomes.find_one(
            {
                "incident_id": inc_id,
                "status": "verified",
                "verified_at": {"$ne": None},
            },
            sort=[("verified_at", -1), ("created_at", -1)],
        )
        if verified_fix:
            enriched["verification_status"] = "verified"
            enriched["resolution_summary"] = verified_fix.get("description")
        else:
            latest_fix = self.db.fix_outcomes.find_one(
                {"incident_id": inc_id},
                sort=[("created_at", -1)],
            )
            if latest_fix:
                latest_stat = latest_fix.get("status")
                if latest_stat in ("failed", "reverted"):
                    enriched["verification_status"] = "failed"
                else:
                    enriched["verification_status"] = "unverified"
            elif not enriched.get("verification_status"):
                enriched["verification_status"] = "unverified"

            # Strict Unverified Fix Guarantee: Unverified/failed fixes must never leak as proven solutions
            if enriched.get("verification_status") != "verified":
                enriched["resolution_summary"] = None

        enriched["is_public"] = bool(enriched.get("is_public", False))
        enriched["disclose_project_id"] = bool(enriched.get("disclose_project_id", False))
        return enriched

    def get_project_incidents(self, project_id: str) -> List[Dict[str, Any]]:
        """Retrieve stored historical incidents for a specific project."""
        query: Dict[str, Any] = {"project_id": project_id}
        if self.current_incident_id:
            query["incident_id"] = {"$ne": self.current_incident_id}
        cursor = self.db.incidents.find(query, {"_id": 0})
        return [self._enrich_incident(doc) for doc in cursor]

    def get_cross_project_incidents(self, requesting_project_id: str) -> List[Dict[str, Any]]:
        """Retrieve cross-project incident candidates strictly filtered by is_public=True."""
        query: Dict[str, Any] = {
            "project_id": {"$ne": requesting_project_id},
            "is_public": True,
        }
        if self.current_incident_id:
            query["incident_id"] = {"$ne": self.current_incident_id}
        cursor = self.db.incidents.find(query, {"_id": 0})
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
    incident: Optional[Dict[str, Any]] = None,
    run: Optional[Dict[str, Any]] = None,
    llm_skipped: Optional[bool] = None,
    decision_reason: Optional[str] = None,
    llm_client: Optional[Any] = None,
) -> DiagnosisCreate:
    """Map ai_engine DiagnosisResponse to backend's DiagnosisCreate persistence model with root-cause refinement."""
    is_verified = (ai_resp.fix_status == ai_schemas.FixStatus.VERIFIED)

    # Determine accurate source string reflecting decision gate / provider provenance
    if decision_reason in (
        DecisionReason.EXACT_VERIFIED_FIX.value,
        DecisionReason.SIMILAR_VERIFIED_RESOLUTION.value,
    ):
        source = "memory/verified-fix"
    elif decision_reason == DecisionReason.GENERAL_KNOWLEDGE_MATCH.value:
        source = "knowledge_base/curated"
    elif decision_reason == DecisionReason.REDACTION_SECURITY_FAILURE.value:
        source = "security/blocked-policy"
    elif decision_reason == DecisionReason.EXTERNAL_INFERENCE_DISABLED.value:
        source = "fallback/local-knowledge"
    elif ai_resp.uncertainty_description and "fallback" in ai_resp.uncertainty_description.lower():
        source = "fallback/local-knowledge"
    elif llm_client is not None and (
        "mock" in type(llm_client).__name__.lower()
        or "mock" in type(getattr(llm_client, "underlying_client", None)).__name__.lower()
    ):
        source = "ai_engine/mock"
    elif os.getenv("GROQ_API_KEY") and not (
        os.getenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "").lower() in ("1", "true", "yes")
        or os.getenv("DEVMEMORY_OFFLINE_MODE", "").lower() in ("1", "true", "yes")
        or os.getenv("AI_PRIVACY_OFFLINE_ONLY", "").lower() in ("1", "true", "yes")
    ):
        source = "ai_engine/groq-llama-3.3-70b"
    else:
        source = "ai_engine/mock"

    # Default mapping from ai_resp
    summary = ai_resp.summary[:2000]
    likely_cause = getattr(ai_resp, "likely_cause", None)
    if likely_cause:
        likely_cause = str(likely_cause)[:3000]
    suggested_fix = "; ".join(ai_resp.recommended_steps) if ai_resp.recommended_steps else None
    confidence = ai_resp.confidence
    evidence_list = ai_resp.evidence[:100]
    hypotheses_causes = ai_resp.hypotheses

    # Apply precision root-cause refinement only when incident context is present and NOT an authorized verified fix
    if incident and not is_verified:
        refinement = refine_root_cause_diagnosis(
            error_type=incident.get("error_type") or "",
            error_message=incident.get("error_message") or "",
            source_snippet=incident.get("source_snippet"),
            stack_trace=incident.get("stack_trace") or (run.get("stderr") if run else ""),
            file_path=incident.get("file_path"),
            line=incident.get("line"),
            column=incident.get("column"),
            ai_summary=ai_resp.summary,
            ai_likely_cause=getattr(ai_resp, "likely_cause", None),
            ai_recommended_steps=ai_resp.recommended_steps,
            ai_hypotheses=ai_resp.hypotheses,
            ai_evidence=ai_resp.evidence,
        )
        if refinement.is_refined:
            summary = refinement.summary[:2000]
            likely_cause = refinement.likely_cause[:3000]
            suggested_fix = refinement.suggested_fix[:5000]
            confidence = refinement.confidence
            evidence_list = refinement.evidence[:100]
            hypotheses_causes = refinement.hypotheses

    if suggested_fix and len(suggested_fix) > 5000:
        suggested_fix = suggested_fix[:5000]

    hypotheses = [
        HypothesisItem(
            cause=h[:1000],
            is_observed=False,
            details=None,
        )
        for h in hypotheses_causes
    ]

    matched_memory = [
        MatchedMemoryRef(
            source_id=m.incident_id[:128],
            source_type=m.match_source.value,
            relevance_reason=m.explanation[:1000] if m.explanation else None,
        )
        for m in ai_resp.related_incidents
    ]

    return DiagnosisCreate(
        summary=summary,
        likely_cause=likely_cause,
        hypotheses=hypotheses,
        suggested_fix=suggested_fix,
        matched_memory=matched_memory,
        evidence=evidence_list,
        confidence=confidence,
        source=source,
        is_verified_fix=is_verified,
        llm_skipped=llm_skipped,
        decision_reason=decision_reason,
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


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime is offset-aware in UTC for safe comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


DEFAULT_DIAGNOSIS_LEASE_SECONDS = 60.0


def generate_and_store_incident_diagnosis(
    db: Database,
    incident_id: str,
    allow_cross_project: bool = True,
    has_cross_project_read: bool = False,
    disable_external_inference: Optional[bool] = None,
    threshold: float = 0.60,
    force_recheck: bool = False,
    fresh_analysis: bool = False,
    lease_timeout_seconds: float = DEFAULT_DIAGNOSIS_LEASE_SECONDS,
    llm_client: Optional[Any] = None,
) -> Tuple[BackendDiagnosisResponseModel, bool]:
    """Execute AI diagnosis for an incident and persist the structured diagnosis in MongoDB.

    Guarantees:
    1. Idempotency: Returns existing latest diagnosis if already diagnosed and force_recheck and fresh_analysis are False.
    2. Atomic Ownership: Acquires recoverable diagnosis lease; prevents concurrent redundant diagnoses.
    3. Stale Worker Protection: Verifies ownership before updating status; stale workers cannot overwrite active state.
    4. Self-Healing Reconciliation: Recovers from crashes between diagnosis insertion and incident status update.
    5. Clean Ownership Rollback: Releases lease on error only if ownership token matches.
    6. LLM Decision Gate: Bypasses external LLM invocation when reliable verified fixes or curated general knowledge exist.
    """
    incident = db.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    now = datetime.now(timezone.utc)

    # 1. Idempotency and Self-Healing Pre-Check (when NOT force_recheck and NOT fresh_analysis)
    if not force_recheck and not fresh_analysis:
        # If already marked diagnosed, short-circuit immediately without invoking LLM
        if incident.get("diagnosis_status") == "diagnosed":
            existing = diagnosis_service.get_latest_diagnosis(db, incident_id)
            if existing:
                existing.idempotent = True
                return existing, False
            # Self-healing: Marked diagnosed but no diagnosis document exists in DB
            db.incidents.update_one(
                {"incident_id": incident_id},
                {"$set": {"diagnosis_status": "pending"}},
            )
            incident["diagnosis_status"] = "pending"

        # Self-healing reconciliation: check if a diagnosis document already exists
        # (e.g. from an earlier worker crash after diagnoses.insert_one but before incident status update)
        existing_doc = db.diagnoses.find_one(
            {"incident_id": incident_id},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        if existing_doc:
            expires_at = _normalize_utc(incident.get("diagnosis_lease_expires_at"))
            # If not actively held by an unexpired lease, reconcile immediately
            if incident.get("diagnosis_status") != "diagnosing" or (expires_at and expires_at < now):
                db.incidents.update_one(
                    {"incident_id": incident_id},
                    {
                        "$set": {"diagnosis_status": "diagnosed"},
                        "$unset": {"diagnosis_lease_token": "", "diagnosis_lease_expires_at": ""},
                    },
                )
                reconciled_resp = BackendDiagnosisResponseModel(**existing_doc)
                reconciled_resp.idempotent = True
                return reconciled_resp, False

    # 2. Check for active unexpired lease held by another worker
    if incident.get("diagnosis_status") == "diagnosing":
        expires_at = _normalize_utc(incident.get("diagnosis_lease_expires_at"))
        if expires_at and expires_at >= now:
            # Active lease in progress by another worker
            # If (force_recheck or fresh_analysis) and existing diagnosis exists, return it, else 409
            existing = diagnosis_service.get_latest_diagnosis(db, incident_id) if (force_recheck or fresh_analysis) else None
            if existing:
                existing.idempotent = True
                return existing, False
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Diagnosis is currently in progress by another worker.",
            )

    # 3. Atomic Lease Acquisition via find_one_and_update
    lease_token = f"lease_{uuid4().hex[:12]}"
    lease_expires_at = now + timedelta(seconds=lease_timeout_seconds)

    lease_query: Dict[str, Any] = {
        "incident_id": incident_id,
        "$or": [
            {"diagnosis_status": "pending"},
            {"diagnosis_status": {"$exists": False}},
            {"diagnosis_status": {"$in": ["failed", "unverified"]}},
            {
                "diagnosis_status": "diagnosing",
                "diagnosis_lease_expires_at": {"$lt": now},
            },
        ],
    }
    if force_recheck or fresh_analysis:
        lease_query["$or"].append({"diagnosis_status": "diagnosed"})

    lease_update = {
        "$set": {
            "diagnosis_status": "diagnosing",
            "diagnosis_lease_token": lease_token,
            "diagnosis_lease_expires_at": lease_expires_at,
        }
    }

    acquired_inc = db.incidents.find_one_and_update(
        lease_query,
        lease_update,
        return_document=ReturnDocument.AFTER,
    )

    if acquired_inc is None:
        # Failed to acquire lease (race condition with concurrent request)
        current_inc = db.incidents.find_one({"incident_id": incident_id})
        if current_inc and current_inc.get("diagnosis_status") == "diagnosed" and not force_recheck and not fresh_analysis:
            existing = diagnosis_service.get_latest_diagnosis(db, incident_id)
            if existing:
                existing.idempotent = True
                return existing, False

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diagnosis is currently in progress by another worker.",
        )

    # 4. Execute AI Diagnosis with Ownership-Aware Cleanup
    try:
        run = None
        event_id = acquired_inc.get("event_id")
        if event_id:
            run = db.command_runs.find_one({"event_id": event_id}, {"_id": 0})

        req, auth = build_ai_diagnosis_payloads(
            incident=acquired_inc,
            run=run,
            allow_cross_project=allow_cross_project,
            has_cross_project_read=has_cross_project_read,
        )

        repo = MongoIncidentRepository(db, current_incident_id=incident_id)

        # Wire production vector adapter and active embedding provider
        settings = get_settings()
        v_idx = os.getenv("MONGODB_VECTOR_INDEX") or settings.MONGODB_VECTOR_INDEX or "idx_incidents_vector"
        v_field = os.getenv("MONGODB_VECTOR_FIELD") or settings.MONGODB_VECTOR_FIELD or "embedding"
        active_embedding_prov = get_active_embedding_provider()
        vector_adapter = ProductionMongoVectorSearchAdapter(
            db=db,
            index_name=v_idx,
            vector_field=v_field,
            embedding_provider=active_embedding_prov,
        )

        # Wire audited LLM client to ensure all outbound payloads are verified and audited
        if isinstance(llm_client, AuditedLLMClient):
            audited_client = llm_client
        else:
            audited_client = get_audited_llm_client(
                db=db,
                project_id=acquired_inc.get("project_id", ""),
                incident_id=incident_id,
                event_id=event_id,
                underlying_client=llm_client,
            )

        # Step 1: Pre-retrieve memory using three-level retrieval (Lexical + Exact + Vector)
        retrieval_result = retrieve_memory(
            request=req,
            auth_context=auth,
            repository=repo,
            threshold=threshold,
            vector_adapter=vector_adapter,
            embedding_provider=active_embedding_prov,
        )

        # Step 2: Evaluate Decision Gate before any external LLM invocation
        is_offline = bool(disable_external_inference) or (
            os.getenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "").lower() in ("1", "true", "yes")
            or os.getenv("DEVMEMORY_OFFLINE_MODE", "").lower() in ("1", "true", "yes")
            or os.getenv("AI_PRIVACY_OFFLINE_ONLY", "").lower() in ("1", "true", "yes")
            or (settings.DEV_MEMORY_DISABLE_EXTERNAL_AI or "").lower() in ("1", "true", "yes")
        )

        gate_eval = evaluate_decision_gate(
            request=req,
            auth_context=auth,
            retrieval_result=retrieval_result,
            fresh_analysis=fresh_analysis,
            disable_external_inference=is_offline,
        )

        if gate_eval.should_call_llm:
            # Insufficient evidence, ambiguous error, or explicit fresh-analysis -> Dispatch LLM
            ai_resp = diagnose_error(
                request=req,
                auth_context=auth,
                repository=repo,
                threshold=threshold,
                disable_external_inference=disable_external_inference,
                vector_adapter=vector_adapter,
                embedding_provider=active_embedding_prov,
                llm_client=audited_client,
            )
            llm_skipped = False
        else:
            # Verified fix, curated knowledge, policy block, or offline -> Zero LLM calls
            ai_resp = gate_eval.synthesized_response
            llm_skipped = True

        decision_reason = gate_eval.decision_reason
        logger.info(
            "Incident %s diagnosis decision gate: should_call_llm=%s, llm_skipped=%s, reason=%s",
            incident_id,
            gate_eval.should_call_llm,
            llm_skipped,
            decision_reason,
        )

        # Map AI response to backend diagnosis schema
        backend_payload = map_ai_response_to_backend_diagnosis(
            ai_resp=ai_resp,
            incident_id=incident_id,
            incident=acquired_inc,
            run=run,
            llm_skipped=llm_skipped,
            decision_reason=decision_reason,
            llm_client=audited_client,
        )

        # Stale Worker Protection: Verify lease token is still active before writing
        verify_inc = db.incidents.find_one({"incident_id": incident_id})
        if verify_inc and verify_inc.get("diagnosis_lease_token") != lease_token:
            # Lease expired and was acquired by another worker!
            # Do NOT write diagnosis or change status.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Diagnosis lease expired or ownership changed prior to persistence.",
            )

        # Persist diagnosis and update status using lease_token
        diagnosis_resp, is_new = diagnosis_service.create_diagnosis(
            db=db,
            incident_id=incident_id,
            payload=backend_payload,
            lease_token=lease_token,
        )

        # Correlate diagnosis_id back to audit records for this incident
        if diagnosis_resp and getattr(diagnosis_resp, "diagnosis_id", None):
            try:
                db.llm_request_audits.update_many(
                    {"incident_id": incident_id, "diagnosis_id": None},
                    {"$set": {"diagnosis_id": diagnosis_resp.diagnosis_id}},
                )
            except Exception as audit_link_exc:
                logger.debug("Failed to link diagnosis_id to llm_request_audits: %s", audit_link_exc)

        # Record decision gate outcome on the incident document for traceability
        try:
            db.incidents.update_one(
                {"incident_id": incident_id},
                {
                    "$set": {
                        "llm_skipped": llm_skipped,
                        "decision_reason": decision_reason,
                        "is_verified_fix": backend_payload.is_verified_fix,
                    }
                },
            )
        except Exception as inc_audit_exc:
            logger.debug("Failed to record decision gate outcome on incident: %s", inc_audit_exc)

        return diagnosis_resp, is_new

    except Exception as exc:
        # Conditional, ownership-aware lease rollback:
        # Only reset to 'pending' if the lease token still matches our token!
        # Do not overwrite if another worker already took ownership!
        if not (isinstance(exc, HTTPException) and exc.status_code == status.HTTP_409_CONFLICT):
            db.incidents.update_one(
                {
                    "incident_id": incident_id,
                    "diagnosis_lease_token": lease_token,
                },
                {
                    "$set": {"diagnosis_status": "pending"},
                    "$unset": {
                        "diagnosis_lease_token": "",
                        "diagnosis_lease_expires_at": "",
                    },
                },
            )
        raise


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
