"""Hybrid retrieval fusion and multi-signal ranking for DevMemory.

Combines:
1. Exact error-signature matches (highest deterministic certainty).
2. Lexical token & stack-frame similarity (explainable rule-based matching).
3. Semantic vector search (MongoDB Atlas / in-memory cosine similarity).

CRITICAL ARCHITECTURAL PRINCIPLE:
Semantic vector similarity is NOT proof that two incidents have the same root cause.
High vector similarity must NEVER override contradictory error types (e.g. KeyError vs
SyntaxError) or incompatible runtime contexts (e.g. Python vs Node.js).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ai_engine.matching import (
    calculate_similarity,
    compute_error_signature,
    extract_exception_type,
    normalize_error_message,
)
from ai_engine.privacy import redact_secrets, sanitize_file_path
from ai_engine.schemas import (
    DiagnosisRequest,
    FixVerificationStatus,
    IncidentMatch,
    MatchSource,
)
from ai_engine.vector import VectorSearchResult

logger = logging.getLogger(__name__)


def detect_technology_stack(command: Optional[str], file_path: Optional[str]) -> Optional[str]:
    """Detect primary language/runtime stack from command or file extension."""
    combined = f"{command or ''} {file_path or ''}".lower()
    if any(k in combined for k in ("python", "pytest", "manage.py", ".py")):
        return "python"
    if any(k in combined for k in ("node", "npm", "yarn", "vite", "tsc", ".js", ".ts", ".jsx", ".tsx")):
        return "javascript_node"
    if any(k in combined for k in ("cargo", "rustc", ".rs")):
        return "rust"
    if any(k in combined for k in ("go run", "go test", ".go")):
        return "golang"
    return None


def calculate_hybrid_score(
    query_request: DiagnosisRequest,
    candidate_dict: Dict[str, Any],
    lexical_score: float,
    vector_score: Optional[float],
) -> Tuple[float, str]:
    """Calculate fused hybrid score with strict evidence-contradiction guards.
    
    Returns:
        (fused_score, explanation_details)
    """
    q_err = query_request.error_message
    q_stack = query_request.stack_trace or ""
    q_cmd = query_request.command

    c_err = candidate_dict.get("error_message", "")
    c_stack = candidate_dict.get("stack_trace", "")
    c_cmd = candidate_dict.get("command", "")

    # 1. Exact Signature Check
    q_sig = compute_error_signature(q_err, q_stack, q_cmd)
    c_sig = candidate_dict.get("error_signature") or compute_error_signature(c_err, c_stack, c_cmd)
    is_exact_sig = bool(c_sig and q_sig == c_sig)

    # 2. Exception Type Contradiction Guard
    q_type = extract_exception_type(q_err, q_stack)
    c_type = extract_exception_type(c_err, c_stack)
    has_contradictory_type = False
    if q_type and c_type and q_type.lower() != c_type.lower():
        has_contradictory_type = True

    # 3. Technology / Stack Compatibility
    q_tech = detect_technology_stack(q_cmd, q_stack)
    c_tech = detect_technology_stack(c_cmd, c_stack)
    has_incompatible_tech = bool(q_tech and c_tech and q_tech != c_tech)

    # 4. Resolution Reliability Signal
    v_status_raw = candidate_dict.get("verification_status", FixVerificationStatus.UNVERIFIED)
    v_status = (
        v_status_raw
        if isinstance(v_status_raw, FixVerificationStatus)
        else FixVerificationStatus(str(v_status_raw).lower())
    )
    reliability_boost = 0.05 if v_status == FixVerificationStatus.VERIFIED else 0.0

    # 5. Hybrid Score Calculation
    explanation_parts: List[str] = []

    if is_exact_sig:
        fused = max(0.98, lexical_score)
        explanation_parts.append(f"Exact error signature match ({q_sig})")
    elif vector_score is not None:
        if has_contradictory_type:
            # Semantic similarity must NOT override contradictory exception types!
            # Heavy penalty discounting semantic contribution
            fused = min(lexical_score * 0.7, 0.35)
            explanation_parts.append(
                f"Contradictory exception type ('{q_type}' vs '{c_type}'); "
                f"semantic score ({vector_score:.0%}) discounted due to conflicting error evidence"
            )
        elif has_incompatible_tech:
            # Cross-technology discrepancy (e.g. Python vs Node)
            fused = (0.60 * lexical_score + 0.40 * vector_score) * 0.75
            explanation_parts.append(
                f"Incompatible runtime stack ('{q_tech}' vs '{c_tech}'); "
                f"hybrid score discounted"
            )
        else:
            # Balanced multi-signal fusion: 55% lexical rules + 45% vector semantics
            fused = 0.55 * lexical_score + 0.45 * vector_score + reliability_boost
            explanation_parts.append(
                f"Hybrid fusion (Lexical: {lexical_score:.0%}, Semantic: {vector_score:.0%})"
            )
    else:
        # Lexical-only path (e.g. when vector service is disabled or offline)
        fused = lexical_score + reliability_boost
        explanation_parts.append(f"Lexical match ({lexical_score:.0%})")

    if reliability_boost > 0 and not is_exact_sig:
        explanation_parts.append("Precedent verified by test execution")

    # Clamp strictly to [0.0, 1.0]
    final_score = round(max(0.0, min(1.0, fused)), 4)
    explanation = "; ".join(explanation_parts)

    return final_score, explanation


def fuse_candidates(
    query_request: DiagnosisRequest,
    lexical_matches: List[IncidentMatch],
    vector_matches: List[VectorSearchResult],
    match_source: MatchSource,
    threshold: float = 0.60,
) -> List[IncidentMatch]:
    """Combine, deduplicate, and re-rank candidate incidents from lexical and vector retrieval streams.
    
    Guarantees:
    - Deduplication by incident_id.
    - Preserves verification status.
    - Sanitizes resolution summaries and paths.
    - Generates explainable match justifications.
    - Enforces threshold filtering and sorts descending by score.
    """
    by_id: Dict[str, Dict[str, Any]] = {}

    # 1. Collect Lexical Matches
    for lex in lexical_matches:
        by_id[lex.incident_id] = {
            "incident_id": lex.incident_id,
            "project_id": lex.project_id,
            "error_message": "",
            "stack_trace": None,
            "command": None,
            "resolution_summary": lex.resolution_summary,
            "verification_status": lex.verification_status,
            "lexical_match": lex,
            "vector_match": None,
            "lexical_score": lex.similarity_score,
            "vector_score": None,
        }

    # 2. Collect Vector Matches & Deduplicate
    for vec in vector_matches:
        if vec.incident_id in by_id:
            by_id[vec.incident_id]["vector_match"] = vec
            by_id[vec.incident_id]["vector_score"] = vec.similarity_score
            if not by_id[vec.incident_id]["resolution_summary"]:
                by_id[vec.incident_id]["resolution_summary"] = vec.resolution_summary
        else:
            # Query lexical score for vector-only candidate to ensure balanced signals
            cand_dict = {
                "error_message": vec.error_message,
                "stack_trace": vec.stack_trace or "",
                "command": vec.command or "",
            }
            query_dict = {
                "error_message": query_request.error_message,
                "stack_trace": query_request.stack_trace or "",
                "command": query_request.command,
            }
            lex_score, _ = calculate_similarity(query_dict, cand_dict)

            by_id[vec.incident_id] = {
                "incident_id": vec.incident_id,
                "project_id": vec.project_id,
                "error_message": vec.error_message,
                "stack_trace": vec.stack_trace,
                "command": vec.command,
                "resolution_summary": vec.resolution_summary,
                "verification_status": vec.verification_status,
                "lexical_match": None,
                "vector_match": vec,
                "lexical_score": lex_score,
                "vector_score": vec.similarity_score,
            }

    # 3. Score and Rank Fused Candidates
    fused_results: List[IncidentMatch] = []

    for item in by_id.values():
        cand_dict = {
            "error_message": item["error_message"] or (item["lexical_match"].explanation if item["lexical_match"] else ""),
            "stack_trace": item["stack_trace"] or "",
            "command": item["command"] or "",
            "verification_status": item["verification_status"],
            "error_signature": item["vector_match"].error_signature if item["vector_match"] else None,
        }

        score, details = calculate_hybrid_score(
            query_request=query_request,
            candidate_dict=cand_dict,
            lexical_score=item["lexical_score"],
            vector_score=item["vector_score"],
        )

        if score >= threshold:
            raw_res = item["resolution_summary"]
            safe_res = redact_secrets(sanitize_file_path(raw_res)) if raw_res else None
            safe_expl = redact_secrets(sanitize_file_path(details))

            fused_results.append(
                IncidentMatch(
                    incident_id=item["incident_id"],
                    project_id=item["project_id"],
                    match_source=match_source,
                    similarity_score=score,
                    explanation=safe_expl,
                    resolution_summary=safe_res,
                    verification_status=item["verification_status"],
                )
            )

    fused_results.sort(key=lambda m: m.similarity_score, reverse=True)
    return fused_results
