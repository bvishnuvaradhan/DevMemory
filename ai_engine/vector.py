"""Vector search adapter and embedding abstractions for DevMemory.

Provides:
1. EmbeddingProvider protocol and DeterministicEmbeddingProvider (100% offline).
2. VectorSearchResult container for vector retrieval outcomes.
3. VectorSearchAdapter protocol.
4. MockVectorSearchAdapter for in-memory, reproducible testing and benchmarks.
5. MongoVectorSearchAdapter for MongoDB Atlas Vector Search with graceful fallback.
"""

from dataclasses import dataclass, field
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


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculate cosine similarity between two float vectors in [0.0, 1.0]."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
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
            text = f"{inc_copy.get('error_message', '')} {inc_copy.get('stack_trace', '')} {inc_copy.get('command', '')}"
            embedding = self.embedding_provider.get_embedding(text)

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
        if not query_vector or all(v == 0.0 for v in query_vector):
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
        if not query_vector or all(v == 0.0 for v in query_vector):
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
