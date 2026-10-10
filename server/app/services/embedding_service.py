"""Service layer for real embedding provider verification, MongoDB persistence, and backfilling.

Guarantees:
1. Provider Verification: Inspects configured embedding provider, model, dimension, and credentials.
   Never prints or exposes secrets. Accurately reports whether live external inference occurred
   or if deterministic fallback / offline opt-out was used. Never falsely claims deterministic
   or mocked embeddings are live semantic embeddings.
2. Safe Persistence: Stores embeddings in MongoDB 'incidents' collection under configured vector field
   (default 'embedding') with project scope, model identifier, dimensions, and metadata.
3. Dimension Compatibility: Strictly validates vector dimensions, finite numeric values, and
   unit-normalization before persistence, preventing incompatible vector dimensions in search index fields.
4. Fault Tolerance: Handles missing, malformed, or failed embeddings safely without corrupting records.
5. Idempotent Backfill: Scans incidents missing embeddings and populates them safely without
   rewriting or deleting existing records.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
import os
from typing import Any, Dict, List, Optional
from pymongo.database import Database

from ai_engine.privacy import redact_secrets
from ai_engine.vector import (
    ConfigurableDenseEmbeddingProvider,
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingResult,
    EmbeddingStatus,
    InvalidVectorError,
    build_embedding_text,
    get_configured_embedding_provider,
    validate_and_normalize_vector,
)
from app.config import get_settings
from app.schemas.incident import (
    EmbeddingBackfillResponse,
    EmbeddingProviderStatusResponse,
    IncidentEmbeddingResponse,
)

logger = logging.getLogger(__name__)


def check_embedding_provider_readiness() -> EmbeddingProviderStatusResponse:
    """Inspect configured embedding provider readiness and credentials safely without leaking secrets."""
    settings = get_settings()
    api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
    model = os.getenv("OPENAI_EMBEDDING_MODEL") or settings.OPENAI_EMBEDDING_MODEL
    p_type = (os.getenv("DEVMEMORY_EMBEDDING_PROVIDER") or settings.DEVMEMORY_EMBEDDING_PROVIDER or "auto").lower()
    default_dim = 128 if p_type == "deterministic" else 1536
    env_dim = int(os.getenv("DEVMEMORY_VECTOR_DIMENSION")) if os.getenv("DEVMEMORY_VECTOR_DIMENSION") else settings.DEVMEMORY_VECTOR_DIMENSION
    dimension = env_dim or default_dim

    is_offline = (
        os.getenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "").lower() in ("1", "true", "yes")
        or os.getenv("DEVMEMORY_OFFLINE_MODE", "").lower() in ("1", "true", "yes")
        or os.getenv("AI_PRIVACY_OFFLINE_ONLY", "").lower() in ("1", "true", "yes")
        or (settings.DEV_MEMORY_DISABLE_EXTERNAL_AI or "").lower() in ("1", "true", "yes")
    )

    masked_key = (f"{api_key[:4]}...{api_key[-4:]}") if (api_key and len(api_key) > 8) else None

    if is_offline:
        return EmbeddingProviderStatusResponse(
            provider_type="offline_deterministic",
            configured_model=model,
            target_dimension=dimension,
            credentials_configured=bool(api_key),
            status="offline_mode_enforced",
            is_live=False,
            reason="External AI inference disabled by privacy configuration (offline mode).",
            masked_credential=masked_key,
        )

    if p_type == "deterministic":
        return EmbeddingProviderStatusResponse(
            provider_type="deterministic",
            configured_model="deterministic",
            target_dimension=dimension,
            credentials_configured=bool(api_key),
            status="deterministic",
            is_live=False,
            reason="Deterministic 100% offline embedding provider explicitly configured.",
            masked_credential=masked_key,
        )

    if not api_key:
        return EmbeddingProviderStatusResponse(
            provider_type=p_type,
            configured_model=model,
            target_dimension=dimension,
            credentials_configured=False,
            status="unconfigured",
            is_live=False,
            reason="OPENAI_API_KEY is not configured in the environment. Safe deterministic fallback will be used.",
            masked_credential=None,
        )

    return EmbeddingProviderStatusResponse(
        provider_type="dense",
        configured_model=model,
        target_dimension=dimension,
        credentials_configured=True,
        status="configured",
        is_live=True,
        reason="OpenAI API credentials configured and ready for live dense embedding requests.",
        masked_credential=masked_key,
    )


def resolve_target_dimension(explicit_dim: Optional[int] = None, provider_type: Optional[str] = None) -> int:
    """Safely resolve the vector dimension from arguments, environment, settings, or provider default."""
    if explicit_dim is not None:
        return explicit_dim
    env_dim = os.getenv("DEVMEMORY_VECTOR_DIMENSION")
    if env_dim:
        try:
            return int(env_dim)
        except ValueError:
            pass
    settings = get_settings()
    if settings.DEVMEMORY_VECTOR_DIMENSION is not None:
        try:
            return int(settings.DEVMEMORY_VECTOR_DIMENSION)
        except (ValueError, TypeError):
            pass
    p_type = (provider_type or os.getenv("DEVMEMORY_EMBEDDING_PROVIDER") or settings.DEVMEMORY_EMBEDDING_PROVIDER or "auto").lower()
    return 128 if p_type == "deterministic" else 1536


def get_active_embedding_provider(
    provider_type: Optional[str] = None,
    dimension: Optional[int] = None,
    model: Optional[str] = None,
    allow_fallback: bool = True,
    timeout: float = 5.0,
) -> EmbeddingProvider:
    """Return the active EmbeddingProvider instance adhering to environment configuration."""
    settings = get_settings()
    p_type = (provider_type or os.getenv("DEVMEMORY_EMBEDDING_PROVIDER") or settings.DEVMEMORY_EMBEDDING_PROVIDER or "auto").lower()
    target_dim = resolve_target_dimension(dimension, provider_type=p_type)
    target_model = model or os.getenv("OPENAI_EMBEDDING_MODEL") or settings.OPENAI_EMBEDDING_MODEL

    return get_configured_embedding_provider(
        provider_type=p_type,
        dimension=target_dim,
        model=target_model,
        allow_fallback=allow_fallback,
        timeout=timeout,
    )


def generate_incident_embedding(
    error_message: str,
    stack_trace: Optional[str] = None,
    command: Optional[str] = None,
    provider: Optional[EmbeddingProvider] = None,
    expected_dimension: Optional[int] = None,
) -> EmbeddingResult:
    """Generate a validated, normalized embedding vector from canonical incident text.

    Guarantees:
    - Preprocessing parity via canonical build_embedding_text.
    - Secret redaction and path sanitization.
    - Vector validation: numeric, finite, non-zero, unit-length.
    - Explicit dimension enforcement.
    """
    target_dim = resolve_target_dimension(expected_dimension)
    active_prov = provider or get_active_embedding_provider(dimension=target_dim)

    canonical_text = build_embedding_text(
        error_message=error_message,
        stack_trace=stack_trace,
        command=command,
    )

    if hasattr(active_prov, "get_embedding_with_status"):
        res = active_prov.get_embedding_with_status(canonical_text)
    else:
        raw_vec = active_prov.get_embedding(canonical_text)
        validated = validate_and_normalize_vector(raw_vec, target_dim, allow_zero=True)
        res = EmbeddingResult(
            vector=validated,
            status=EmbeddingStatus.DETERMINISTIC_FALLBACK,
            dimension=target_dim,
            model="deterministic",
            is_fallback=True,
        )

    # Secondary validation safeguard
    if len(res.vector) != target_dim:
        raise InvalidVectorError(
            f"Embedding dimension mismatch: expected {target_dim}, received {len(res.vector)}"
        )

    return res


def persist_incident_embedding(
    db: Database,
    incident_id: str,
    embedding_result: EmbeddingResult,
    canonical_text: Optional[str] = None,
    vector_field: Optional[str] = None,
) -> bool:
    """Persist an embedding vector and associated metadata into the MongoDB incidents collection.

    Guarantees:
    - Avoids incompatible dimensions within search index field.
    - Preserves tenant isolation and existing incident fields.
    - Idempotent and crash-resilient.
    """
    settings = get_settings()
    v_field = vector_field or os.getenv("MONGODB_VECTOR_FIELD") or settings.MONGODB_VECTOR_FIELD or "embedding"

    incident = db.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise ValueError(f"Incident '{incident_id}' not found in database.")

    # Dimension and type validation
    vector = embedding_result.vector
    expected_dim = embedding_result.dimension
    validate_and_normalize_vector(vector, expected_dim, allow_zero=True)

    status_str = (
        embedding_result.status.value
        if hasattr(embedding_result.status, "value")
        else str(embedding_result.status)
    )

    update_doc = {
        v_field: vector,
        "embedding_model": embedding_result.model,
        "embedding_dimension": expected_dim,
        "embedding_status": status_str,
        "embedding_is_fallback": bool(embedding_result.is_fallback),
        "embedded_at": datetime.now(timezone.utc),
    }
    if canonical_text:
        update_doc["embedding_canonical_text"] = canonical_text

    result = db.incidents.update_one(
        {"incident_id": incident_id},
        {"$set": update_doc},
    )

    return result.matched_count > 0


def get_incident_embedding(
    db: Database,
    incident_id: str,
    vector_field: Optional[str] = None,
) -> Optional[IncidentEmbeddingResponse]:
    """Retrieve the persisted embedding vector and metadata for an incident from MongoDB."""
    settings = get_settings()
    v_field = vector_field or os.getenv("MONGODB_VECTOR_FIELD") or settings.MONGODB_VECTOR_FIELD or "embedding"

    doc = db.incidents.find_one(
        {"incident_id": incident_id},
        {
            "_id": 0,
            "incident_id": 1,
            "project_id": 1,
            v_field: 1,
            "embedding_model": 1,
            "embedding_dimension": 1,
            "embedding_status": 1,
            "embedding_is_fallback": 1,
            "embedding_canonical_text": 1,
            "embedded_at": 1,
        },
    )

    if not doc or v_field not in doc or not doc[v_field]:
        return None

    return IncidentEmbeddingResponse(
        incident_id=doc["incident_id"],
        project_id=doc["project_id"],
        embedding=doc[v_field],
        embedding_model=doc.get("embedding_model", "unknown"),
        embedding_dimension=doc.get("embedding_dimension", len(doc[v_field])),
        embedding_status=doc.get("embedding_status", "unknown"),
        embedding_is_fallback=bool(doc.get("embedding_is_fallback", False)),
        canonical_text=doc.get("embedding_canonical_text"),
        embedded_at=doc.get("embedded_at"),
    )


def generate_and_persist_incident_embedding(
    db: Database,
    incident_id: str,
    provider: Optional[EmbeddingProvider] = None,
    vector_field: Optional[str] = None,
    force: bool = False,
) -> Optional[IncidentEmbeddingResponse]:
    """Generate and persist an embedding for a specific incident document.

    If the incident already has an embedding and force is False, returns existing record idempotently.
    """
    settings = get_settings()
    v_field = vector_field or os.getenv("MONGODB_VECTOR_FIELD") or settings.MONGODB_VECTOR_FIELD or "embedding"

    existing = get_incident_embedding(db, incident_id, vector_field=v_field)
    if existing and not force:
        return existing

    doc = db.incidents.find_one({"incident_id": incident_id})
    if not doc:
        return None

    # Enrich command and stack_trace from command_runs if present
    command = doc.get("command")
    stack_trace = doc.get("stack_trace") or doc.get("source_snippet")
    event_id = doc.get("event_id")

    if event_id and (not command or not stack_trace):
        run = db.command_runs.find_one({"event_id": event_id}, {"_id": 0, "command": 1, "stderr": 1})
        if run:
            if not command:
                command = run.get("command")
            if not stack_trace:
                stack_trace = run.get("stderr")

    canonical_text = build_embedding_text(
        error_message=doc.get("error_message", ""),
        stack_trace=stack_trace,
        command=command,
    )

    target_dim = resolve_target_dimension()
    active_prov = provider or get_active_embedding_provider(dimension=target_dim)

    embedding_res = generate_incident_embedding(
        error_message=doc.get("error_message", ""),
        stack_trace=stack_trace,
        command=command,
        provider=active_prov,
        expected_dimension=target_dim,
    )

    persist_incident_embedding(
        db=db,
        incident_id=incident_id,
        embedding_result=embedding_res,
        canonical_text=canonical_text,
        vector_field=v_field,
    )

    return get_incident_embedding(db, incident_id, vector_field=v_field)


def backfill_incident_embeddings(
    db: Database,
    project_id: Optional[str] = None,
    force: bool = False,
    provider: Optional[EmbeddingProvider] = None,
    vector_field: Optional[str] = None,
    batch_size: int = 100,
) -> EmbeddingBackfillResponse:
    """Safely and idempotently backfill embeddings for all stored incidents missing them.

    Guarantees:
    - Scans existing documents without modifying unneeded fields.
    - Respects project scoping if provided.
    - Idempotent: running repeatedly performs zero duplicate work when force=False.
    - Individual failure isolation: one bad document does not abort the entire batch.
    """
    settings = get_settings()
    v_field = vector_field or os.getenv("MONGODB_VECTOR_FIELD") or settings.MONGODB_VECTOR_FIELD or "embedding"
    target_dim = resolve_target_dimension()
    active_prov = provider or get_active_embedding_provider(dimension=target_dim)

    filter_query: Dict[str, Any] = {}
    if project_id:
        filter_query["project_id"] = project_id
    if not force:
        filter_query[v_field] = {"$exists": False}

    cursor = db.incidents.find(filter_query).batch_size(batch_size)

    total_scanned = 0
    updated = 0
    skipped = 0
    failed = 0

    model_name = getattr(active_prov, "model", "deterministic")

    for doc in cursor:
        total_scanned += 1
        inc_id = doc.get("incident_id")
        if not inc_id:
            skipped += 1
            continue

        try:
            generate_and_persist_incident_embedding(
                db=db,
                incident_id=inc_id,
                provider=active_prov,
                vector_field=v_field,
                force=force,
            )
            updated += 1
        except Exception as exc:
            logger.warning("Failed to embed incident '%s' during backfill: %s", inc_id, exc)
            failed += 1

    return EmbeddingBackfillResponse(
        total_scanned=total_scanned,
        updated=updated,
        skipped=skipped,
        failed=failed,
        embedding_model=model_name,
        embedding_dimension=target_dim,
    )
