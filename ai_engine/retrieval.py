"""Three-level memory retrieval architecture for DevMemory AI & Memory Engine.

Coordinates deterministic retrieval across:
1. Level 1: Curated General Knowledge (offline, no API key required).
2. Level 2: Project-Specific Historical Memory.
3. Level 3: Authorized Cross-Project Precedents (privacy-filtered, server-authorized).
"""

import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, ConfigDict, Field

from ai_engine.knowledge import get_default_knowledge_base
from ai_engine.matching import (
    calculate_similarity,
    compute_error_signature,
    normalize_error_message,
)
from ai_engine.privacy import (
    is_cross_project_sharing_permitted,
    redact_secrets,
    sanitize_file_path,
)
from ai_engine.schemas import (
    DiagnosisRequest,
    FixVerificationStatus,
    IncidentMatch,
    KnowledgeBaseItem,
    MatchSource,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class IncidentRepository(Protocol):
    """Repository protocol abstracting incident persistence for retrieval."""

    def get_project_incidents(self, project_id: str) -> List[Dict[str, Any]]:
        """Retrieve stored historical incidents for a specific project."""
        ...

    def get_cross_project_incidents(self, requesting_project_id: str) -> List[Dict[str, Any]]:
        """Retrieve potential cross-project incident candidates from other projects."""
        ...


class InMemoryIncidentRepository:
    """In-memory incident repository adapter for testing and offline execution."""

    def __init__(self, incidents: Optional[List[Dict[str, Any]]] = None) -> None:
        self._incidents: List[Dict[str, Any]] = list(incidents or [])

    def add_incident(self, incident: Dict[str, Any]) -> None:
        self._incidents.append(incident)

    def get_project_incidents(self, project_id: str) -> List[Dict[str, Any]]:
        return [inc for inc in self._incidents if inc.get("project_id") == project_id]

    def get_cross_project_incidents(self, requesting_project_id: str) -> List[Dict[str, Any]]:
        return [inc for inc in self._incidents if inc.get("project_id") != requesting_project_id]


class AuthorizationContext(BaseModel):
    """Context supplied by the trusted backend to verify identity and rights.
    
    CRITICAL: Client-supplied request flags must never supersede this server context.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str = Field(..., min_length=1, description="Authenticated user identifier")
    project_id: str = Field(..., min_length=1, description="Authorized active project identifier")
    has_project_access: bool = Field(
        default=True,
        description="Whether user has read access to the current project",
    )
    has_cross_project_read: bool = Field(
        default=False,
        description="Server-side grant permitting cross-project memory search",
    )


class RetrievalResult(BaseModel):
    """Container for three-level memory retrieval outcomes."""
    model_config = ConfigDict(extra="forbid")

    general_matches: List[IncidentMatch] = Field(default_factory=list)
    project_matches: List[IncidentMatch] = Field(default_factory=list)
    cross_project_matches: List[IncidentMatch] = Field(default_factory=list)
    all_ranked_matches: List[IncidentMatch] = Field(
        default_factory=list,
        description="Consolidated and ranked matches across all authorized levels",
    )


def _match_general_knowledge(
    request: DiagnosisRequest,
    kb_items: List[KnowledgeBaseItem],
    threshold: float,
) -> List[IncidentMatch]:
    """Retrieve Level 1 general knowledge matches."""
    matches: List[IncidentMatch] = []
    query_dict = {
        "error_message": request.error_message,
        "stack_trace": request.stack_trace or "",
        "command": request.command,
    }

    for item in kb_items:
        cand_dict = {
            "error_pattern": item.error_pattern,
            "error_message": item.error_pattern,
            "explanation": item.explanation,
        }
        score, explanation = calculate_similarity(query_dict, cand_dict)
        if score >= threshold:
            resolutions = "; ".join(item.suggested_resolutions[:3])
            matches.append(
                IncidentMatch(
                    incident_id=item.kb_id,
                    project_id=None,
                    match_source=MatchSource.GENERAL_KNOWLEDGE,
                    similarity_score=score,
                    explanation=f"{item.title}: {explanation}",
                    resolution_summary=f"Suggested resolutions: {resolutions}",
                    verification_status=FixVerificationStatus.UNVERIFIED,
                )
            )

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches


def _match_project_memory(
    request: DiagnosisRequest,
    candidates: List[Dict[str, Any]],
    threshold: float,
) -> List[IncidentMatch]:
    """Retrieve Level 2 current-project memory matches."""
    matches: List[IncidentMatch] = []
    query_dict = {
        "error_message": request.error_message,
        "stack_trace": request.stack_trace or "",
        "command": request.command,
    }

    for cand in candidates:
        cand_dict = {
            "error_message": cand.get("error_message", ""),
            "stack_trace": cand.get("stack_trace", ""),
            "command": cand.get("command", ""),
        }
        score, explanation = calculate_similarity(query_dict, cand_dict)

        # Boost score slightly if exact error signature matches
        q_sig = compute_error_signature(request.error_message, request.stack_trace, request.command)
        c_sig = cand.get("error_signature")
        if c_sig and q_sig == c_sig:
            score = max(score, 0.98)
            explanation = f"Exact error signature match ({q_sig}); " + explanation

        if score >= threshold:
            v_status_raw = cand.get("verification_status", FixVerificationStatus.UNVERIFIED)
            v_status = (
                v_status_raw
                if isinstance(v_status_raw, FixVerificationStatus)
                else FixVerificationStatus(str(v_status_raw).lower())
            )

            matches.append(
                IncidentMatch(
                    incident_id=cand.get("incident_id", "unknown_incident"),
                    project_id=request.project_id,
                    match_source=MatchSource.PROJECT_MEMORY,
                    similarity_score=score,
                    explanation=explanation,
                    resolution_summary=cand.get("resolution_summary"),
                    verification_status=v_status,
                )
            )

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches


def _match_cross_project_memory(
    request: DiagnosisRequest,
    candidates: List[Dict[str, Any]],
    threshold: float,
    auth_context: AuthorizationContext,
) -> List[IncidentMatch]:
    """Retrieve Level 3 authorized, privacy-filtered cross-project matches."""
    matches: List[IncidentMatch] = []

    # Server authorization check: must have explicit cross-project grant
    if not auth_context.has_cross_project_read:
        logger.info("Cross-project retrieval omitted: server authorization missing.")
        return matches

    query_dict = {
        "error_message": request.error_message,
        "stack_trace": request.stack_trace or "",
        "command": request.command,
    }

    for cand in candidates:
        cand_proj = cand.get("project_id", "")
        cand_is_public = bool(cand.get("is_public", False))

        # Check server policy and user client preference
        permitted = is_cross_project_sharing_permitted(
            requester_project_id=request.project_id,
            candidate_project_id=cand_proj,
            candidate_is_public=cand_is_public,
            requester_prefers_cross_project=request.allow_cross_project,
        )
        if not permitted:
            continue

        cand_dict = {
            "error_message": cand.get("error_message", ""),
            "stack_trace": cand.get("stack_trace", ""),
            "command": cand.get("command", ""),
        }
        score, explanation = calculate_similarity(query_dict, cand_dict)
        if score >= threshold:
            v_status_raw = cand.get("verification_status", FixVerificationStatus.UNVERIFIED)
            v_status = (
                v_status_raw
                if isinstance(v_status_raw, FixVerificationStatus)
                else FixVerificationStatus(str(v_status_raw).lower())
            )

            # Privacy filtering: sanitize resolution summary, redact secrets and machine paths
            raw_res = cand.get("resolution_summary")
            sanitized_res = redact_secrets(sanitize_file_path(raw_res)) if raw_res else None

            # Disclose project_id only if permitted by source policy
            disclosed_project_id = cand_proj if cand.get("disclose_project_id", False) else None

            matches.append(
                IncidentMatch(
                    incident_id=cand.get("incident_id", "cross_proj_incident"),
                    project_id=disclosed_project_id,
                    match_source=MatchSource.CROSS_PROJECT,
                    similarity_score=score,
                    explanation=f"Cross-project precedent: {explanation}",
                    resolution_summary=sanitized_res,
                    verification_status=v_status,
                )
            )

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches


def retrieve_memory(
    request: DiagnosisRequest,
    auth_context: AuthorizationContext,
    repository: Optional[IncidentRepository] = None,
    kb_items: Optional[List[KnowledgeBaseItem]] = None,
    threshold: float = 0.60,
) -> RetrievalResult:
    """Orchestrate three-level memory retrieval.
    
    Guarantees:
    - Level 1 operates offline without database or network.
    - Level 2 restricts results strictly to request.project_id.
    - Level 3 strictly requires auth_context.has_cross_project_read and public sharing.
    - Fault isolation: failure in one level does not crash remaining levels.
    """
    general_matches: List[IncidentMatch] = []
    project_matches: List[IncidentMatch] = []
    cross_project_matches: List[IncidentMatch] = []

    # 1. Level 1: General Knowledge
    try:
        items = kb_items if kb_items is not None else get_default_knowledge_base()
        general_matches = _match_general_knowledge(request, items, threshold)
    except Exception as exc:
        logger.warning("Level 1 general knowledge retrieval failed: %s", exc)

    # 2. Level 2: Project Memory
    if repository and auth_context.has_project_access and (auth_context.project_id == request.project_id):
        try:
            cand_list = repository.get_project_incidents(request.project_id)
            project_matches = _match_project_memory(request, cand_list, threshold)
        except Exception as exc:
            logger.warning("Level 2 project memory retrieval failed: %s", exc)

    # 3. Level 3: Cross-Project Memory
    if repository:
        try:
            cand_cross = repository.get_cross_project_incidents(request.project_id)
            cross_project_matches = _match_cross_project_memory(
                request, cand_cross, threshold, auth_context
            )
        except Exception as exc:
            logger.warning("Level 3 cross-project memory retrieval failed: %s", exc)

    # Consolidated ranking across all levels
    all_matches = general_matches + project_matches + cross_project_matches
    # Prioritize project matches slightly on identical score, sort by score descending
    all_matches.sort(
        key=lambda m: (m.similarity_score, 1 if m.match_source == MatchSource.PROJECT_MEMORY else 0),
        reverse=True,
    )

    return RetrievalResult(
        general_matches=general_matches,
        project_matches=project_matches,
        cross_project_matches=cross_project_matches,
        all_ranked_matches=all_matches,
    )
