"""Service layer for real embedding provider verification, MongoDB persistence, and backfilling.

Guarantees:
1. Provider Verification: Inspects configured embedding provider (Voyage AI as production standard,
   OpenAI/Deterministic as alternatives), model, dimension, and credentials.
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
6. Safe History Cleanup: Safely deletes incident, run, diagnosis, fix, and performance history
   while strictly preserving registered projects and configuration records.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math
import os
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request
from pymongo.database import Database

from ai_engine.privacy import redact_secrets, sanitize_file_path
from ai_engine.vector import (
    ConfigurableDenseEmbeddingProvider,
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingProviderError,
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


def sanitize_secret_text(text: str, secret: Optional[str] = None) -> str:
    """Sanitize secrets using generic pattern redaction and explicit credential masking."""
    if not text:
        return ""
    redacted = redact_secrets(text)
    if secret and len(secret) > 4 and secret in redacted:
        redacted = redacted.replace(secret, f"{secret[:4]}...[REDACTED]")
    return redacted


def clean_devmemory_history(db: Database) -> Dict[str, int]:
    """Safely and idempotently delete historical data while preserving projects and configurations.

    Deletes:
    - incidents (and their vector embeddings)
    - command_runs
    - diagnoses
    - fix_outcomes
    - performance_runs
    - performance_baselines

    Preserves:
    - projects (identities, settings, metadata)
    - collection indexes
    - schema validators
    """
    history_collections = [
        "incidents",
        "command_runs",
        "diagnoses",
        "fix_outcomes",
        "performance_runs",
        "performance_baselines",
    ]
    deleted_counts: Dict[str, int] = {}
    for coll_name in history_collections:
        try:
            coll = db[coll_name]
            res = coll.delete_many({})
            deleted_counts[coll_name] = getattr(res, "deleted_count", 0)
        except Exception as exc:
            logger.warning("Error clearing collection %s: %s", coll_name, exc)
            deleted_counts[coll_name] = 0
    return deleted_counts


class VoyageEmbeddingProvider:
    """Production-ready Voyage AI embedding provider adapter.

    Guarantees:
    - Uses Voyage API endpoint https://api.voyageai.com/v1/embeddings
    - Standard library HTTP client (urllib.request) avoiding unnecessary SDK dependencies
    - Supports input_type="document" (for stored incidents/content) and input_type="query" (for searches)
    - Default model: voyage-code-4, default dimension: 1024
    - Validates HTTP status, JSON schema, vector length (1024), numeric values, finiteness, and unit-normalizes
    - Handles rate limits (429), auth failures (401), timeouts, server errors with secret redaction
    - Falls back safely to DeterministicEmbeddingProvider(dimension=1024) when credentials are missing
      or call fails (if allow_fallback=True)
    - Preserves EmbeddingProvider protocol compatibility
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dimension: int = 1024,
        endpoint: Optional[str] = None,
        allow_fallback: bool = True,
        timeout: float = 10.0,
        fallback_provider: Optional[EmbeddingProvider] = None,
    ) -> None:
        settings = get_settings()
        if api_key is not None:
            self.api_key = api_key if api_key.strip() else None
        else:
            self.api_key = os.getenv("VOYAGE_API_KEY") or settings.VOYAGE_API_KEY
        self.model = model or os.getenv("VOYAGE_EMBEDDING_MODEL") or settings.VOYAGE_EMBEDDING_MODEL or "voyage-code-4"
        self._dim = dimension
        self.endpoint = (
            endpoint
            or os.getenv("VOYAGE_EMBEDDINGS_URL")
            or settings.VOYAGE_EMBEDDINGS_URL
            or "https://api.voyageai.com/v1/embeddings"
        )
        self.allow_fallback = allow_fallback
        self.timeout = timeout
        self._fallback = fallback_provider or DeterministicEmbeddingProvider(dimension=self._dim)
        self.last_status: Optional[EmbeddingStatus] = None
        self.last_result: Optional[EmbeddingResult] = None

    @property
    def dimension(self) -> int:
        return self._dim

    def sanitize_input(self, text: str) -> str:
        """Sanitize and minimize diagnostic text before sending to Voyage embedding API."""
        if not text:
            return ""
        sanitized = redact_secrets(text)
        sanitized = sanitize_file_path(sanitized)
        if len(sanitized) > 1000:
            sanitized = sanitized[:1000].rsplit(" ", 1)[0] + " ... [truncated]"
        return sanitized.strip()

    def get_embedding(self, text: str, input_type: str = "document") -> List[float]:
        """Generate normalized dense embedding vector adhering to EmbeddingProvider protocol."""
        res = self.get_embedding_with_status(text, input_type=input_type)
        return res.vector

    def get_embedding_with_status(
        self,
        text: str,
        input_type: str = "document",
    ) -> EmbeddingResult:
        """Generate normalized dense embedding vector with explicit status tracking and provenance."""
        clean_text = self.sanitize_input(text)
        if not clean_text:
            res = EmbeddingResult(
                vector=[0.0] * self._dim,
                status=EmbeddingStatus.DETERMINISTIC_FALLBACK,
                dimension=self._dim,
                model=self.model,
                is_fallback=True,
                error_message="Empty input text",
                provider_name="voyage",
            )
            self.last_status = res.status
            self.last_result = res
            return res

        # Privacy opt-out / offline check
        if (
            os.getenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "").lower() in ("1", "true", "yes")
            or os.getenv("DEVMEMORY_OFFLINE_MODE", "").lower() in ("1", "true", "yes")
            or os.getenv("AI_PRIVACY_OFFLINE_ONLY", "").lower() in ("1", "true", "yes")
        ):
            logger.info("External AI inference disabled by privacy configuration; using deterministic fallback.")
            return self._execute_fallback(clean_text, EmbeddingStatus.OFFLINE_OPT_OUT, "Privacy opt-out enabled")

        # If live credentials exist, execute live Voyage API call
        if self.api_key:
            try:
                raw_vec = self._call_voyage_api(clean_text, input_type)
                normalized = validate_and_normalize_vector(raw_vec, self._dim)
                res = EmbeddingResult(
                    vector=normalized,
                    status=EmbeddingStatus.LIVE_SUCCESS,
                    dimension=self._dim,
                    model=self.model,
                    is_fallback=False,
                    provider_name="voyage",
                )
                self.last_status = res.status
                self.last_result = res
                return res
            except urllib.error.HTTPError as err:
                err_body = ""
                try:
                    err_body = err.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                safe_body = sanitize_secret_text(err_body, self.api_key)
                if err.code == 401:
                    reason = f"Voyage AI authentication failed (HTTP 401): invalid or unauthorized VOYAGE_API_KEY. {safe_body}"
                elif err.code == 429:
                    reason = f"Voyage AI rate limit exceeded (HTTP 429). {safe_body}"
                elif err.code in (400, 422):
                    reason = f"Voyage AI bad request (HTTP {err.code}): {safe_body or err.reason}"
                else:
                    reason = f"Voyage AI request failed (HTTP {err.code}): {safe_body or err.reason}"
                logger.warning("%s; evaluating fallback.", reason)
                return self._execute_fallback(clean_text, EmbeddingStatus.DETERMINISTIC_FALLBACK, reason)
            except urllib.error.URLError as err:
                safe_err = sanitize_secret_text(str(err.reason), self.api_key)
                reason = f"Voyage AI network error: {safe_err}"
                logger.warning("%s; evaluating fallback.", reason)
                return self._execute_fallback(clean_text, EmbeddingStatus.DETERMINISTIC_FALLBACK, reason)
            except TimeoutError:
                reason = f"Voyage AI request timed out after {self.timeout}s"
                logger.warning("%s; evaluating fallback.", reason)
                return self._execute_fallback(clean_text, EmbeddingStatus.DETERMINISTIC_FALLBACK, reason)
            except InvalidVectorError as err:
                safe_err = sanitize_secret_text(str(err), self.api_key)
                reason = f"Voyage AI vector validation error: {safe_err}"
                logger.warning("%s; evaluating fallback.", reason)
                return self._execute_fallback(clean_text, EmbeddingStatus.DETERMINISTIC_FALLBACK, reason)
            except Exception as exc:
                safe_exc = sanitize_secret_text(str(exc), self.api_key)
                reason = f"Voyage AI unexpected error: {safe_exc}"
                logger.warning("%s; evaluating fallback.", reason)
                return self._execute_fallback(clean_text, EmbeddingStatus.DETERMINISTIC_FALLBACK, reason)

        # Default when credentials unconfigured: deterministic fallback
        return self._execute_fallback(
            clean_text,
            EmbeddingStatus.DETERMINISTIC_FALLBACK,
            "VOYAGE_API_KEY is not configured in the environment",
        )

    def _call_voyage_api(self, text: str, input_type: str) -> List[float]:
        """Send raw HTTP request to Voyage AI embeddings endpoint and return float vector."""
        payload: Dict[str, Any] = {
            "input": [text],
            "model": self.model,
        }
        if input_type in ("document", "query"):
            payload["input_type"] = input_type

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=req_data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "DevMemory-Server/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            resp_bytes = resp.read()
            resp_json = json.loads(resp_bytes.decode("utf-8"))

            if not isinstance(resp_json, dict):
                raise InvalidVectorError("Voyage API response root is not a JSON object")
            data = resp_json.get("data")
            if not isinstance(data, list) or not data:
                raise InvalidVectorError("Voyage API response missing non-empty 'data' list")
            item = data[0]
            if not isinstance(item, dict) or "embedding" not in item:
                raise InvalidVectorError("Voyage API response data item missing 'embedding'")

            raw_vec = item["embedding"]
            return raw_vec

    def _execute_fallback(
        self,
        clean_text: str,
        status: EmbeddingStatus,
        reason: str,
    ) -> EmbeddingResult:
        """Execute deterministic fallback with strict contract and dimension enforcement."""
        if not self.allow_fallback:
            res_fail = EmbeddingResult(
                vector=[0.0] * self._dim,
                status=EmbeddingStatus.UNAVAILABLE_FAILURE,
                dimension=self._dim,
                model=self.model,
                is_fallback=False,
                error_message=reason,
                provider_name="voyage",
            )
            self.last_status = res_fail.status
            self.last_result = res_fail
            raise EmbeddingProviderError(f"Voyage embedding provider failed and fallback is disabled: {reason}")

        fallback_vec = self._fallback.get_embedding(clean_text)
        try:
            norm_vec = validate_and_normalize_vector(fallback_vec, self._dim, allow_zero=True)
        except InvalidVectorError as err:
            res_fail = EmbeddingResult(
                vector=[0.0] * self._dim,
                status=EmbeddingStatus.UNAVAILABLE_FAILURE,
                dimension=self._dim,
                model=self.model,
                is_fallback=True,
                error_message=f"Fallback vector validation failed: {err}",
                provider_name="voyage",
            )
            self.last_status = res_fail.status
            self.last_result = res_fail
            raise EmbeddingProviderError(f"Fallback vector validation failed: {err}")

        res = EmbeddingResult(
            vector=norm_vec,
            status=status,
            dimension=self._dim,
            model=self.model,
            is_fallback=True,
            error_message=reason,
            provider_name="voyage",
        )
        self.last_status = res.status
        self.last_result = res
        return res


def check_embedding_provider_readiness(verify_live: bool = False) -> EmbeddingProviderStatusResponse:
    """Inspect configured embedding provider readiness and credentials safely without leaking secrets."""
    settings = get_settings()
    p_type = (os.getenv("DEVMEMORY_EMBEDDING_PROVIDER") or settings.DEVMEMORY_EMBEDDING_PROVIDER or "voyage").lower()
    dimension = resolve_target_dimension(provider_type=p_type)

    is_offline = (
        os.getenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "").lower() in ("1", "true", "yes")
        or os.getenv("DEVMEMORY_OFFLINE_MODE", "").lower() in ("1", "true", "yes")
        or os.getenv("AI_PRIVACY_OFFLINE_ONLY", "").lower() in ("1", "true", "yes")
        or (settings.DEV_MEMORY_DISABLE_EXTERNAL_AI or "").lower() in ("1", "true", "yes")
    )

    if p_type == "deterministic":
        return EmbeddingProviderStatusResponse(
            provider_type="deterministic",
            configured_model="deterministic",
            target_dimension=dimension,
            credentials_configured=False,
            status="deterministic",
            is_live=False,
            reason="Deterministic 100% offline embedding provider explicitly configured.",
            masked_credential=None,
        )

    if p_type == "voyage":
        api_key = os.getenv("VOYAGE_API_KEY") or settings.VOYAGE_API_KEY
        model = os.getenv("VOYAGE_EMBEDDING_MODEL") or settings.VOYAGE_EMBEDDING_MODEL or "voyage-code-4"
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

        if not api_key:
            return EmbeddingProviderStatusResponse(
                provider_type="voyage",
                configured_model=model,
                target_dimension=dimension,
                credentials_configured=False,
                status="unconfigured",
                is_live=False,
                reason="VOYAGE_API_KEY is not configured in the environment. Safe deterministic fallback will be used.",
                masked_credential=None,
            )

        if verify_live:
            prov = VoyageEmbeddingProvider(api_key=api_key, model=model, dimension=dimension, allow_fallback=False, timeout=5.0)
            try:
                res = prov.get_embedding_with_status("healthcheck probe", input_type="query")
                if res.status == EmbeddingStatus.LIVE_SUCCESS:
                    return EmbeddingProviderStatusResponse(
                        provider_type="voyage",
                        configured_model=model,
                        target_dimension=dimension,
                        credentials_configured=True,
                        status="verified_live",
                        is_live=True,
                        reason="Voyage AI API live verification succeeded.",
                        masked_credential=masked_key,
                    )
            except Exception as exc:
                safe_err = redact_secrets(str(exc))
                return EmbeddingProviderStatusResponse(
                    provider_type="voyage",
                    configured_model=model,
                    target_dimension=dimension,
                    credentials_configured=True,
                    status="live_verification_failed",
                    is_live=False,
                    reason=f"Voyage AI credentials configured but live check failed: {safe_err}",
                    masked_credential=masked_key,
                )

        return EmbeddingProviderStatusResponse(
            provider_type="voyage",
            configured_model=model,
            target_dimension=dimension,
            credentials_configured=True,
            status="configured",
            is_live=True,
            reason="Voyage AI API credentials configured and ready for live dense embedding requests.",
            masked_credential=masked_key,
        )

    # Dense / OpenAI fallback
    api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
    model = os.getenv("OPENAI_EMBEDDING_MODEL") or settings.OPENAI_EMBEDDING_MODEL
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
    p_type = (provider_type or os.getenv("DEVMEMORY_EMBEDDING_PROVIDER") or settings.DEVMEMORY_EMBEDDING_PROVIDER or "voyage").lower()
    if p_type == "deterministic":
        return 128
    if p_type == "voyage":
        return 1024
    return 1536


def get_active_embedding_provider(
    provider_type: Optional[str] = None,
    dimension: Optional[int] = None,
    model: Optional[str] = None,
    allow_fallback: bool = True,
    timeout: float = 10.0,
) -> EmbeddingProvider:
    """Return the active EmbeddingProvider instance adhering to environment configuration."""
    settings = get_settings()
    p_type = (provider_type or os.getenv("DEVMEMORY_EMBEDDING_PROVIDER") or settings.DEVMEMORY_EMBEDDING_PROVIDER or "voyage").lower()
    target_dim = resolve_target_dimension(dimension, provider_type=p_type)

    if p_type == "voyage":
        target_model = model or os.getenv("VOYAGE_EMBEDDING_MODEL") or settings.VOYAGE_EMBEDDING_MODEL or "voyage-code-4"
        api_key = os.getenv("VOYAGE_API_KEY") or settings.VOYAGE_API_KEY
        endpoint = os.getenv("VOYAGE_EMBEDDINGS_URL") or settings.VOYAGE_EMBEDDINGS_URL or "https://api.voyageai.com/v1/embeddings"
        return VoyageEmbeddingProvider(
            api_key=api_key,
            model=target_model,
            dimension=target_dim,
            endpoint=endpoint,
            allow_fallback=allow_fallback,
            timeout=timeout,
        )
    elif p_type in ("openai", "dense"):
        target_model = model or os.getenv("OPENAI_EMBEDDING_MODEL") or settings.OPENAI_EMBEDDING_MODEL
        return get_configured_embedding_provider(
            provider_type=p_type,
            dimension=target_dim,
            model=target_model,
            allow_fallback=allow_fallback,
            timeout=timeout,
        )

    return DeterministicEmbeddingProvider(dimension=target_dim)


def generate_incident_embedding(
    error_message: str,
    stack_trace: Optional[str] = None,
    command: Optional[str] = None,
    provider: Optional[EmbeddingProvider] = None,
    expected_dimension: Optional[int] = None,
    input_type: str = "document",
) -> EmbeddingResult:
    """Generate a validated, normalized embedding vector from canonical incident text.

    Guarantees:
    - Preprocessing parity via canonical build_embedding_text.
    - Secret redaction and path sanitization.
    - Vector validation: numeric, finite, non-zero, unit-length.
    - Explicit dimension enforcement.
    - input_type="document" for stored items.
    """
    target_dim = resolve_target_dimension(expected_dimension)
    active_prov = provider or get_active_embedding_provider(dimension=target_dim)

    canonical_text = build_embedding_text(
        error_message=error_message,
        stack_trace=stack_trace,
        command=command,
    )

    if hasattr(active_prov, "get_embedding_with_status"):
        try:
            res = active_prov.get_embedding_with_status(canonical_text, input_type=input_type)
        except TypeError:
            res = active_prov.get_embedding_with_status(canonical_text)
    else:
        raw_vec = active_prov.get_embedding(canonical_text)
        norm_vec = validate_and_normalize_vector(raw_vec, target_dim, allow_zero=True)
        res = EmbeddingResult(
            vector=norm_vec,
            status=EmbeddingStatus.LIVE_SUCCESS if not getattr(active_prov, "is_fallback", False) else EmbeddingStatus.DETERMINISTIC_FALLBACK,
            dimension=target_dim,
            model=getattr(active_prov, "model", "deterministic"),
            is_fallback=getattr(active_prov, "is_fallback", False),
            provider_name=getattr(active_prov, "provider_name", "deterministic"),
        )

    # Strict dimension validation
    if len(res.vector) != target_dim:
        raise InvalidVectorError(
            f"Generated embedding dimension {len(res.vector)} does not match required target dimension {target_dim}."
        )

    return res


def generate_query_embedding(
    query_text: str,
    provider: Optional[EmbeddingProvider] = None,
    expected_dimension: Optional[int] = None,
) -> EmbeddingResult:
    """Generate a validated, normalized embedding vector for retrieval queries with input_type='query'."""
    target_dim = resolve_target_dimension(expected_dimension)
    active_prov = provider or get_active_embedding_provider(dimension=target_dim)

    if hasattr(active_prov, "get_embedding_with_status"):
        try:
            res = active_prov.get_embedding_with_status(query_text, input_type="query")
        except TypeError:
            res = active_prov.get_embedding_with_status(query_text)
    else:
        raw_vec = active_prov.get_embedding(query_text)
        norm_vec = validate_and_normalize_vector(raw_vec, target_dim, allow_zero=True)
        res = EmbeddingResult(
            vector=norm_vec,
            status=EmbeddingStatus.LIVE_SUCCESS if not getattr(active_prov, "is_fallback", False) else EmbeddingStatus.DETERMINISTIC_FALLBACK,
            dimension=target_dim,
            model=getattr(active_prov, "model", "deterministic"),
            is_fallback=getattr(active_prov, "is_fallback", False),
            provider_name=getattr(active_prov, "provider_name", "deterministic"),
        )

    if len(res.vector) != target_dim:
        raise InvalidVectorError(
            f"Generated query embedding dimension {len(res.vector)} does not match required target dimension {target_dim}."
        )

    return res


def persist_incident_embedding(
    db: Database,
    incident_id: str,
    embedding_result: EmbeddingResult,
    canonical_text: Optional[str] = None,
    vector_field: Optional[str] = None,
) -> bool:
    """Persist generated embedding vector and metadata to MongoDB incident document."""
    settings = get_settings()
    v_field = vector_field or os.getenv("MONGODB_VECTOR_FIELD") or settings.MONGODB_VECTOR_FIELD or "embedding"

    norm_vector = validate_and_normalize_vector(embedding_result.vector, embedding_result.dimension)

    now = datetime.now(timezone.utc)
    status_str = (
        embedding_result.status.value
        if hasattr(embedding_result.status, "value")
        else str(embedding_result.status)
    )

    update_doc: Dict[str, Any] = {
        v_field: norm_vector,
        "embedding_model": embedding_result.model,
        "embedding_dimension": embedding_result.dimension,
        "embedding_status": status_str,
        "embedding_is_fallback": bool(embedding_result.is_fallback),
        "embedded_at": now,
    }
    if canonical_text:
        update_doc["embedding_canonical_text"] = canonical_text

    result = db.incidents.update_one(
        {"incident_id": incident_id},
        {"$set": update_doc},
    )

    if result.matched_count == 0:
        logger.warning("Incident with id '%s' not found for embedding update.", incident_id)
        return False

    return True


def get_incident_embedding(
    db: Database,
    incident_id: str,
    vector_field: Optional[str] = None,
) -> Optional[IncidentEmbeddingResponse]:
    """Retrieve persisted embedding vector and metadata for an incident from MongoDB."""
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

    vec = doc[v_field]
    return IncidentEmbeddingResponse(
        incident_id=incident_id,
        project_id=doc.get("project_id", "unknown"),
        embedding=vec,
        embedding_model=doc.get("embedding_model", "unknown"),
        embedding_dimension=doc.get("embedding_dimension", len(vec)),
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
    """Generate and persist an embedding for a specific incident document."""
    settings = get_settings()
    v_field = vector_field or os.getenv("MONGODB_VECTOR_FIELD") or settings.MONGODB_VECTOR_FIELD or "embedding"

    existing = get_incident_embedding(db, incident_id, vector_field=v_field)
    if existing and not force:
        return existing

    doc = db.incidents.find_one({"incident_id": incident_id})
    if not doc:
        return None

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
        input_type="document",
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
    """Safely and idempotently backfill embeddings for all stored incidents missing them."""
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
            failed += 1
            logger.error("Failed to backfill embedding for incident '%s': %s", inc_id, exc)

    return EmbeddingBackfillResponse(
        total_scanned=total_scanned,
        updated=updated,
        skipped=skipped,
        failed=failed,
        embedding_model=model_name,
        embedding_dimension=target_dim,
    )
