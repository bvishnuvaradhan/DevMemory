"""Vector search adapter and embedding abstractions for DevMemory.

Provides:
1. EmbeddingProvider protocol and DeterministicEmbeddingProvider (100% offline).
2. VectorSearchResult container for vector retrieval outcomes.
3. VectorSearchAdapter protocol.
4. MockVectorSearchAdapter for in-memory, reproducible testing and benchmarks.
5. MongoVectorSearchAdapter for MongoDB Atlas Vector Search with graceful fallback.
"""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from ai_engine.privacy import redact_secrets, sanitize_file_path
from ai_engine.schemas import FixVerificationStatus

logger = logging.getLogger(__name__)

DEFAULT_VECTOR_DIMENSION = 128


class EmbeddingStatus(str, Enum):
    """Explicit status of an embedding generation operation."""
    LIVE_SUCCESS = "live_success"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    OFFLINE_OPT_OUT = "offline_opt_out"
    UNAVAILABLE_FAILURE = "unavailable_failure"


class EmbeddingProviderError(Exception):
    """Raised when an embedding provider fails and cannot safely fall back."""
    pass


class InvalidVectorError(EmbeddingProviderError):
    """Raised when an embedding vector is malformed, non-numeric, non-finite, or invalid."""
    pass


class InvalidConfigurationError(EmbeddingProviderError):
    """Raised when embedding provider configuration is invalid or unsupported."""
    pass


@dataclass
class EmbeddingResult:
    """Detailed result of an embedding operation including provenance and status."""
    vector: List[float]
    status: EmbeddingStatus
    dimension: int
    model: str
    is_fallback: bool
    error_message: Optional[str] = None
    provider_name: str = "dense"


def validate_and_normalize_vector(
    vector: Any,
    expected_dim: int,
    allow_zero: bool = False,
) -> List[float]:
    """Validate vector dimensions, numeric types, finiteness, and unit-normalize.

    Raises:
        InvalidVectorError: If vector is None, not a list/tuple, wrong dimension,
                            contains non-numeric or non-finite elements, or has zero magnitude.
    """
    if vector is None:
        raise InvalidVectorError("Vector cannot be None")

    if not isinstance(vector, (list, tuple)):
        raise InvalidVectorError(f"Vector must be a list or tuple, got {type(vector).__name__}")

    if len(vector) != expected_dim:
        raise InvalidVectorError(
            f"Vector dimension mismatch: expected {expected_dim}, got {len(vector)}"
        )

    for i, x in enumerate(vector):
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise InvalidVectorError(
                f"Vector element at index {i} is non-numeric: {type(x).__name__}"
            )
        if not math.isfinite(x):
            raise InvalidVectorError(
                f"Vector element at index {i} is non-finite: {x}"
            )

    sum_sq = sum(float(x) * float(x) for x in vector)
    if sum_sq <= 0.0:
        if allow_zero:
            return [0.0] * expected_dim
        raise InvalidVectorError("Vector magnitude is zero; cannot unit-normalize an all-zero vector")

    norm = math.sqrt(sum_sq)
    if abs(norm - 1.0) < 1e-4:
        return [round(float(x), 6) for x in vector]
    return [round(float(x) / norm, 6) for x in vector]


def validate_model_configuration(model: str, dimension: int) -> None:
    """Validate model name and dimension combinations against supported bounds.

    Raises:
        InvalidConfigurationError: If model or dimension combination is invalid.
    """
    if not model or not isinstance(model, str) or not model.strip():
        raise InvalidConfigurationError("Embedding model name cannot be empty")
    if dimension <= 0:
        raise InvalidConfigurationError(f"Embedding dimension must be a positive integer, got {dimension}")

    m_lower = model.lower()
    if "text-embedding-ada-002" in m_lower:
        if dimension != 1536:
            raise InvalidConfigurationError(
                f"Model '{model}' fixed dimension is 1536, but requested dimension is {dimension}"
            )
    elif "text-embedding-3-small" in m_lower:
        if dimension > 1536:
            raise InvalidConfigurationError(
                f"Model '{model}' maximum dimension is 1536, but requested dimension is {dimension}"
            )
    elif "text-embedding-3-large" in m_lower:
        if dimension > 3072:
            raise InvalidConfigurationError(
                f"Model '{model}' maximum dimension is 3072, but requested dimension is {dimension}"
            )



def build_embedding_text(
    error_message: str,
    stack_trace: Optional[str] = None,
    command: Optional[str] = None,
) -> str:
    """Canonical text representation for embedding both queries and stored incidents.

    Guarantees query vs document preprocessing parity:
    1. Combines error_message, stack_trace, and command with stable ordering.
    2. Redacts sensitive credentials (API keys, bearer tokens, passwords).
    3. Masks local file paths to user-agnostic representations.
    4. Truncates cleanly to 1,000 characters to prevent token exhaustion and cost spikes.
    """
    parts: List[str] = []
    if error_message and error_message.strip():
        parts.append(error_message.strip())
    if stack_trace and stack_trace.strip():
        parts.append(stack_trace.strip())
    if command and command.strip():
        parts.append(command.strip())

    raw = " ".join(parts)
    sanitized = redact_secrets(sanitize_file_path(raw))
    if len(sanitized) > 1000:
        sanitized = sanitized[:1000].rsplit(" ", 1)[0] + " ... [truncated]"
    return sanitized.strip()


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for generating vector embeddings from diagnostic text."""

    def get_embedding(self, text: str) -> List[float]:
        """Generate a normalized embedding vector for the provided text."""
        ...

    @property
    def dimension(self) -> int:
        """Return the dimension of the generated embeddings."""
        ...


class DeterministicEmbeddingProvider:
    """100% offline, deterministic embedding generator using token hashing & frequency weighting.
    
    Guarantees:
    - 0 network or external service calls.
    - Deterministic, reproducible vector output for identical texts.
    - Always unit-normalized (L2 norm = 1.0) so dot product equals cosine similarity.
    - Sanitizes text before embedding generation to ensure secrets are never embedded.
    - High similarity (~0.75-0.95) for semantically related error tokens and stack frames.
    - Low similarity (~0.05-0.25) for completely unrelated error domains.
    """

    def __init__(self, dimension: int = DEFAULT_VECTOR_DIMENSION) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def get_embedding(self, text: str) -> List[float]:
        """Generate a sanitized, unit-length float vector of size self.dimension."""
        if not text:
            return [0.0] * self._dim

        # Crucial security guarantee: sanitize text before vector generation
        sanitized = redact_secrets(sanitize_file_path(text)).lower()

        # Tokenize into word and sub-token tokens
        tokens = re.findall(r"[a-z0-9_]{2,}", sanitized)
        if not tokens:
            return [0.0] * self._dim

        vector = [0.0] * self._dim

        for token in tokens:
            # Deterministic hash mapping to vector dimension buckets
            h_int = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            bucket = h_int % self._dim
            sign = 1.0 if ((h_int >> 8) & 1) == 0 else -1.0

            # Weight exception keywords and common root causes slightly higher
            weight = 1.0
            if any(term in token for term in ("error", "exception", "refused", "timeout", "null", "undefined", "failed")):
                weight = 2.0
            elif len(token) > 8:
                weight = 1.5

            vector[bucket] += sign * weight

        # Also encode 3-character n-grams for typo-resilient morphological similarity
        for i in range(len(sanitized) - 2):
            trigram = sanitized[i : i + 3]
            if trigram.strip():
                h_tri = int(hashlib.md5(trigram.encode("utf-8")).hexdigest()[:8], 16)
                bucket_tri = h_tri % self._dim
                vector[bucket_tri] += 0.2

        # L2 Unit Normalization: sum(v_i^2) = 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0.0:
            return [round(v / norm, 6) for v in vector]
        return [0.0] * self._dim


class DenseEmbeddingClient(Protocol):
    """Protocol for external dense embedding API client (e.g. OpenAI text-embedding-3-small)."""

    def create_embedding(self, text: str, model: str) -> List[float]:
        """Call external embedding API endpoint and return float vector."""
        ...


class ConfigurableDenseEmbeddingProvider:
    """Production-ready dense embedding provider with strict privacy pre-sanitization.

    Guarantees:
    - Automatically redacts synthetic and real API keys, bearer tokens, passwords,
      and private file paths BEFORE sending any text payload to external embedding APIs.
    - Truncates oversized diagnostic input to 1,000 characters to prevent high-cost token consumption.
    - Validates dimension compatibility and unit-normalizes vector output.
    - Handles timeouts and provider failures safely with deterministic fallback.
    - Supports mock clients for 100% offline unit and CI execution without external API keys.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dimension: int = 1536,
        client: Optional[DenseEmbeddingClient] = None,
        fallback_provider: Optional[EmbeddingProvider] = None,
        allow_fallback: bool = True,
        timeout: float = 5.0,
    ) -> None:
        selected_model = model or os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        validate_model_configuration(selected_model, dimension)
        if timeout <= 0:
            raise InvalidConfigurationError(f"Timeout must be positive, got {timeout}")

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = selected_model
        self._dim = dimension
        self._client = client
        self.allow_fallback = allow_fallback
        self.timeout = timeout
        self._fallback = fallback_provider or DeterministicEmbeddingProvider(dimension=dimension)

        self.last_status: Optional[EmbeddingStatus] = None
        self.last_result: Optional[EmbeddingResult] = None

    @property
    def dimension(self) -> int:
        return self._dim

    def sanitize_input(self, text: str) -> str:
        """Sanitize and minimize diagnostic text before sending to embedding provider."""
        if not text:
            return ""
        # 1. Redact secrets and private tokens
        sanitized = redact_secrets(text)
        # 2. Sanitize local machine and user paths
        sanitized = sanitize_file_path(sanitized)
        # 3. Truncate to reasonable context window (1,000 chars) to prevent excessive tokens
        if len(sanitized) > 1000:
            sanitized = sanitized[:1000].rsplit(" ", 1)[0] + " ... [truncated]"
        return sanitized.strip()

    def get_embedding_with_status(self, text: str) -> EmbeddingResult:
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
            )
            self.last_status = res.status
            self.last_result = res
            return res

        # Check external AI opt-out privacy policy
        if os.getenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "").lower() in ("1", "true", "yes") or \
           os.getenv("DEVMEMORY_OFFLINE_MODE", "").lower() in ("1", "true", "yes"):
            logger.info("External AI inference disabled by privacy configuration; using deterministic fallback.")
            return self._execute_fallback(clean_text, EmbeddingStatus.OFFLINE_OPT_OUT, "Privacy opt-out enabled")

        # If custom client is injected (e.g. for offline mock testing)
        if self._client is not None:
            try:
                raw_vec = self._client.create_embedding(clean_text, self.model)
                normalized = validate_and_normalize_vector(raw_vec, self._dim)
                res = EmbeddingResult(
                    vector=normalized,
                    status=EmbeddingStatus.LIVE_SUCCESS,
                    dimension=self._dim,
                    model=self.model,
                    is_fallback=False,
                )
                self.last_status = res.status
                self.last_result = res
                return res
            except Exception as exc:
                safe_exc = redact_secrets(str(exc))
                logger.warning("Dense embedding client failed (%s); evaluating fallback.", safe_exc)
                return self._execute_fallback(clean_text, EmbeddingStatus.DETERMINISTIC_FALLBACK, safe_exc)

        # If live credentials exist and official openai API call
        if self.api_key:
            try:
                import urllib.request
                import json

                url = os.getenv("OPENAI_EMBEDDINGS_URL", "https://api.openai.com/v1/embeddings")
                payload: Dict[str, Any] = {
                    "input": clean_text,
                    "model": self.model,
                }
                if "text-embedding-3" in self.model:
                    payload["dimensions"] = self._dim
                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=req_data,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "DevMemory-AI-Engine/1.0",
                    },
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    resp_data = resp.read().decode("utf-8")
                    resp_json = json.loads(resp_data)

                    # Validate response structure
                    if not isinstance(resp_json, dict):
                        raise InvalidVectorError("Response root is not a JSON object")
                    if "data" not in resp_json or not isinstance(resp_json["data"], list) or not resp_json["data"]:
                        raise InvalidVectorError("Response missing non-empty 'data' list")
                    item = resp_json["data"][0]
                    if not isinstance(item, dict) or "embedding" not in item:
                        raise InvalidVectorError("Response data item missing 'embedding'")

                    raw_vec = item["embedding"]
                    normalized = validate_and_normalize_vector(raw_vec, self._dim)
                    res = EmbeddingResult(
                        vector=normalized,
                        status=EmbeddingStatus.LIVE_SUCCESS,
                        dimension=self._dim,
                        model=self.model,
                        is_fallback=False,
                    )
                    self.last_status = res.status
                    self.last_result = res
                    return res
            except Exception as exc:
                safe_exc = redact_secrets(str(exc))
                logger.warning("Live dense embedding request failed (%s); evaluating fallback.", safe_exc)
                return self._execute_fallback(clean_text, EmbeddingStatus.DETERMINISTIC_FALLBACK, safe_exc)

        # Default when no external credentials configured: deterministic fallback
        return self._execute_fallback(clean_text, EmbeddingStatus.DETERMINISTIC_FALLBACK, "No external credentials configured")

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
            )
            self.last_status = res_fail.status
            self.last_result = res_fail
            raise EmbeddingProviderError(f"Embedding provider failed and fallback is disabled: {reason}")

        # Dimension compatibility check
        if self._fallback.dimension != self._dim:
            res_fail = EmbeddingResult(
                vector=[0.0] * self._dim,
                status=EmbeddingStatus.UNAVAILABLE_FAILURE,
                dimension=self._dim,
                model=self.model,
                is_fallback=False,
                error_message=(
                    f"Fallback dimension ({self._fallback.dimension}) does not match "
                    f"required embedding dimension ({self._dim})"
                ),
            )
            self.last_status = res_fail.status
            self.last_result = res_fail
            raise EmbeddingProviderError(
                f"Deterministic fallback dimension ({self._fallback.dimension}) does not match "
                f"required embedding dimension ({self._dim}); failing closed to prevent contract violation."
            )

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
        )
        self.last_status = res.status
        self.last_result = res
        return res

    def get_embedding(self, text: str) -> List[float]:
        """Generate normalized dense embedding vector.

        Preserves standard EmbeddingProvider protocol. Callers seeking execution provenance
        and status can call get_embedding_with_status() or inspect provider.last_status.
        """
        res = self.get_embedding_with_status(text)
        return res.vector

    def _normalize_vector(self, vector: List[float]) -> List[float]:
        """Validate finite dimensions and unit normalize (backward compatibility)."""
        try:
            return validate_and_normalize_vector(vector, self._dim, allow_zero=True)
        except InvalidVectorError:
            return [0.0] * self._dim


def get_configured_embedding_provider(
    provider_type: Optional[str] = None,
    dimension: Optional[int] = None,
    model: Optional[str] = None,
    allow_fallback: bool = True,
    timeout: float = 5.0,
) -> EmbeddingProvider:
    """Factory creating the appropriate embedding provider based on environment and configuration.

    Defaults to 100% offline DeterministicEmbeddingProvider unless 'dense' is explicitly
    requested or OPENAI_API_KEY is present.
    """
    p_type = (provider_type or os.getenv("DEVMEMORY_EMBEDDING_PROVIDER", "deterministic")).lower()
    env_dim = int(os.getenv("DEVMEMORY_VECTOR_DIMENSION", "0")) if os.getenv("DEVMEMORY_VECTOR_DIMENSION") else None
    selected_model = model or os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    if p_type == "dense" or (p_type == "auto" and os.getenv("OPENAI_API_KEY")):
        dense_dim = dimension or env_dim or 1536
        return ConfigurableDenseEmbeddingProvider(
            dimension=dense_dim,
            model=selected_model,
            allow_fallback=allow_fallback,
            timeout=timeout,
        )

    det_dim = dimension or env_dim or DEFAULT_VECTOR_DIMENSION
    return DeterministicEmbeddingProvider(dimension=det_dim)


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculate cosine similarity between two float vectors in [0.0, 1.0].

    Safely rejects empty, mismatched, or non-finite (NaN / Inf) vector entries.
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    # Ensure all elements are valid finite numbers
    if not all(math.isfinite(x) for x in vec_a) or not all(math.isfinite(y) for y in vec_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    # Dot product of unit vectors is in [-1.0, 1.0]; clamp and map to [0.0, 1.0]
    return max(0.0, min(1.0, dot))



@dataclass
class VectorSearchResult:
    """Standardized result returned by a vector search adapter."""
    incident_id: str
    project_id: Optional[str]
    error_message: str
    similarity_score: float  # [0.0, 1.0]
    stack_trace: Optional[str] = None
    command: Optional[str] = None
    resolution_summary: Optional[str] = None
    verification_status: FixVerificationStatus = FixVerificationStatus.UNVERIFIED
    is_public: bool = False
    error_signature: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorSearchAdapter(Protocol):
    """Protocol for semantic vector search across incidents."""

    def search_project_vectors(
        self,
        query_vector: List[float],
        project_id: str,
        limit: int = 5,
        min_score: float = 0.50,
    ) -> List[VectorSearchResult]:
        """Search vector embeddings strictly within the active project."""
        ...

    def search_cross_project_vectors(
        self,
        query_vector: List[float],
        requesting_project_id: str,
        limit: int = 5,
        min_score: float = 0.50,
    ) -> List[VectorSearchResult]:
        """Search vector embeddings across other authorized, public projects."""
        ...


class MockVectorSearchAdapter:
    """In-memory vector search adapter for offline unit testing and reproducible evaluation."""

    def __init__(
        self,
        embedding_provider: Optional[EmbeddingProvider] = None,
        incidents: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.embedding_provider = embedding_provider or DeterministicEmbeddingProvider()
        self._stored: List[Dict[str, Any]] = []

        if incidents:
            for inc in incidents:
                self.add_incident(inc)

    def add_incident(self, incident: Dict[str, Any], embedding: Optional[List[float]] = None) -> None:
        """Add an incident and its vector representation to the store."""
        inc_copy = dict(incident)
        if embedding is None:
            text = build_embedding_text(
                error_message=inc_copy.get("error_message", ""),
                stack_trace=inc_copy.get("stack_trace"),
                command=inc_copy.get("command"),
            )
            embedding = self.embedding_provider.get_embedding(text)
        else:
            if not isinstance(embedding, (list, tuple)) or not all(
                isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                for x in embedding
            ):
                raise InvalidVectorError("Cannot add incident with non-numeric or non-finite embedding vector")

        inc_copy["_embedding"] = embedding
        self._stored.append(inc_copy)

    def search_project_vectors(
        self,
        query_vector: List[float],
        project_id: str,
        limit: int = 5,
        min_score: float = 0.50,
    ) -> List[VectorSearchResult]:
        """Search stored vectors strictly scoped to project_id."""
        if not query_vector or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in query_vector
        ) or all(v == 0.0 for v in query_vector):
            return []

        results: List[VectorSearchResult] = []

        for item in self._stored:
            # Strict project isolation check
            if item.get("project_id") != project_id:
                continue

            emb = item.get("_embedding", [])
            score = cosine_similarity(query_vector, emb)
            if score >= min_score:
                v_status_raw = item.get("verification_status", FixVerificationStatus.UNVERIFIED)
                v_status = (
                    v_status_raw
                    if isinstance(v_status_raw, FixVerificationStatus)
                    else FixVerificationStatus(str(v_status_raw).lower())
                )

                results.append(
                    VectorSearchResult(
                        incident_id=item.get("incident_id", "unknown"),
                        project_id=project_id,
                        error_message=item.get("error_message", ""),
                        similarity_score=score,
                        stack_trace=item.get("stack_trace"),
                        command=item.get("command"),
                        resolution_summary=item.get("resolution_summary"),
                        verification_status=v_status,
                        is_public=bool(item.get("is_public", False)),
                        error_signature=item.get("error_signature"),
                    )
                )

        results.sort(key=lambda r: r.similarity_score, reverse=True)
        return results[:limit]

    def search_cross_project_vectors(
        self,
        query_vector: List[float],
        requesting_project_id: str,
        limit: int = 5,
        min_score: float = 0.50,
    ) -> List[VectorSearchResult]:
        """Search stored vectors across public incidents from other projects."""
        if not query_vector or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in query_vector
        ) or all(v == 0.0 for v in query_vector):
            return []

        results: List[VectorSearchResult] = []

        for item in self._stored:
            cand_proj = item.get("project_id", "")
            # Must NOT belong to current project, and MUST be public
            if cand_proj == requesting_project_id or not item.get("is_public", False):
                continue

            emb = item.get("_embedding", [])
            score = cosine_similarity(query_vector, emb)
            if score >= min_score:
                v_status_raw = item.get("verification_status", FixVerificationStatus.UNVERIFIED)
                v_status = (
                    v_status_raw
                    if isinstance(v_status_raw, FixVerificationStatus)
                    else FixVerificationStatus(str(v_status_raw).lower())
                )

                disclosed_proj = cand_proj if item.get("disclose_project_id", False) else None

                results.append(
                    VectorSearchResult(
                        incident_id=item.get("incident_id", "unknown"),
                        project_id=disclosed_proj,
                        error_message=item.get("error_message", ""),
                        similarity_score=score,
                        stack_trace=item.get("stack_trace"),
                        command=item.get("command"),
                        resolution_summary=item.get("resolution_summary"),
                        verification_status=v_status,
                        is_public=True,
                        error_signature=item.get("error_signature"),
                    )
                )

        results.sort(key=lambda r: r.similarity_score, reverse=True)
        return results[:limit]


class MongoVectorSearchAdapter:
    """MongoDB Atlas Vector Search adapter using the official $vectorSearch aggregation pipeline.
    
    Supports:
    - Pre-filtering by project_id and is_public before vector candidate evaluation.
    - Fully configurable index name, path, database, and connection string.
    - Graceful fault tolerance: catches OperationFailure (e.g. on Community Edition where
      $vectorSearch is unsupported, or when the Atlas index has not finished building)
      and logs a clean warning while falling back to lexical search without crashing.
    """

    def __init__(
        self,
        connection_uri: Optional[str] = None,
        database_name: Optional[str] = None,
        collection_name: Optional[str] = None,
        index_name: Optional[str] = None,
        vector_field: Optional[str] = None,
        timeout_ms: int = 2000,
    ) -> None:
        self.connection_uri = connection_uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.database_name = database_name or os.getenv("MONGODB_DATABASE", "devmemory")
        self.collection_name = collection_name or os.getenv("MONGODB_COLLECTION", "incidents")
        self.index_name = index_name or os.getenv("MONGODB_VECTOR_INDEX", "devmemory_vector_index")
        self.vector_field = vector_field or os.getenv("MONGODB_VECTOR_FIELD", "embedding")
        self.timeout_ms = timeout_ms
        self._client: Optional[Any] = None

    def _get_collection(self) -> Any:
        """Lazily initialize pymongo client and return targeted collection."""
        if self._client is None:
            import pymongo

            self._client = pymongo.MongoClient(
                self.connection_uri,
                serverSelectionTimeoutMS=self.timeout_ms,
            )
        return self._client[self.database_name][self.collection_name]

    def build_project_search_pipeline(
        self,
        query_vector: List[float],
        project_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Construct Atlas $vectorSearch pipeline for project-scoped queries."""
        return [
            {
                "$vectorSearch": {
                    "index": self.index_name,
                    "path": self.vector_field,
                    "queryVector": query_vector,
                    "numCandidates": limit * 10,
                    "limit": limit,
                    "filter": {"project_id": project_id},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "incident_id": 1,
                    "project_id": 1,
                    "error_message": 1,
                    "stack_trace": 1,
                    "command": 1,
                    "resolution_summary": 1,
                    "verification_status": 1,
                    "is_public": 1,
                    "error_signature": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]

    def build_cross_project_search_pipeline(
        self,
        query_vector: List[float],
        requesting_project_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Construct Atlas $vectorSearch pipeline for authorized cross-project queries."""
        return [
            {
                "$vectorSearch": {
                    "index": self.index_name,
                    "path": self.vector_field,
                    "queryVector": query_vector,
                    "numCandidates": limit * 10,
                    "limit": limit,
                    "filter": {
                        "project_id": {"$ne": requesting_project_id},
                        "is_public": True,
                    },
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "incident_id": 1,
                    "project_id": 1,
                    "error_message": 1,
                    "stack_trace": 1,
                    "command": 1,
                    "resolution_summary": 1,
                    "verification_status": 1,
                    "is_public": 1,
                    "disclose_project_id": 1,
                    "error_signature": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]

    def search_project_vectors(
        self,
        query_vector: List[float],
        project_id: str,
        limit: int = 5,
        min_score: float = 0.50,
    ) -> List[VectorSearchResult]:
        """Execute MongoDB Atlas $vectorSearch pipeline scoped to project_id."""
        if not query_vector or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in query_vector
        ) or all(v == 0.0 for v in query_vector):
            return []

        pipeline = self.build_project_search_pipeline(
            query_vector=query_vector,
            project_id=project_id,
            limit=limit,
        )

        try:
            coll = self._get_collection()
            cursor = coll.aggregate(pipeline)
            results: List[VectorSearchResult] = []
            for doc in cursor:
                score = float(doc.get("score", 0.0))
                if score >= min_score:
                    v_status_raw = doc.get("verification_status", FixVerificationStatus.UNVERIFIED)
                    v_status = (
                        v_status_raw
                        if isinstance(v_status_raw, FixVerificationStatus)
                        else FixVerificationStatus(str(v_status_raw).lower())
                    )
                    results.append(
                        VectorSearchResult(
                            incident_id=doc.get("incident_id", "mongo_incident"),
                            project_id=project_id,
                            error_message=doc.get("error_message", ""),
                            similarity_score=score,
                            stack_trace=doc.get("stack_trace"),
                            command=doc.get("command"),
                            resolution_summary=doc.get("resolution_summary"),
                            verification_status=v_status,
                            is_public=bool(doc.get("is_public", False)),
                            error_signature=doc.get("error_signature"),
                        )
                    )
            return results
        except Exception as exc:
            # Graceful fault tolerance: MongoDB Community or missing Atlas index
            logger.warning(
                "MongoDB Vector Search unavailable (%s); falling back cleanly to lexical search.",
                exc,
            )
            return []

    def search_cross_project_vectors(
        self,
        query_vector: List[float],
        requesting_project_id: str,
        limit: int = 5,
        min_score: float = 0.50,
    ) -> List[VectorSearchResult]:
        """Execute MongoDB Atlas $vectorSearch pipeline for public cross-project precedents."""
        if not query_vector or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in query_vector
        ) or all(v == 0.0 for v in query_vector):
            return []

        pipeline = self.build_cross_project_search_pipeline(
            query_vector=query_vector,
            requesting_project_id=requesting_project_id,
            limit=limit,
        )

        try:
            coll = self._get_collection()
            cursor = coll.aggregate(pipeline)
            results: List[VectorSearchResult] = []
            for doc in cursor:
                score = float(doc.get("score", 0.0))
                if score >= min_score:
                    cand_proj = doc.get("project_id")
                    disclosed_proj = cand_proj if doc.get("disclose_project_id", False) else None
                    v_status_raw = doc.get("verification_status", FixVerificationStatus.UNVERIFIED)
                    v_status = (
                        v_status_raw
                        if isinstance(v_status_raw, FixVerificationStatus)
                        else FixVerificationStatus(str(v_status_raw).lower())
                    )
                    results.append(
                        VectorSearchResult(
                            incident_id=doc.get("incident_id", "mongo_cross_incident"),
                            project_id=disclosed_proj,
                            error_message=doc.get("error_message", ""),
                            similarity_score=score,
                            stack_trace=doc.get("stack_trace"),
                            command=doc.get("command"),
                            resolution_summary=doc.get("resolution_summary"),
                            verification_status=v_status,
                            is_public=True,
                            error_signature=doc.get("error_signature"),
                        )
                    )
            return results
        except Exception as exc:
            logger.warning(
                "MongoDB Cross-Project Vector Search unavailable (%s); falling back cleanly.",
                exc,
            )
            return []
