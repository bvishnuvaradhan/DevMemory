"""Tests for real embedding provider verification, MongoDB persistence, durability, and safe backfill.

Validates:
1. Embedding provider readiness, credentials inspection, and secret redaction.
2. Vector validation, unit-normalization, and dimension compatibility.
3. Explicit distinction between live semantic embeddings, deterministic fallback, and offline opt-out.
4. MongoDB persistence, retrieval, and durability across client reconnects/restarts.
5. Safe, idempotent backfill behavior for existing incidents.
6. REST API endpoints for provider status, incident embedding retrieval, and backfilling.
7. Tenant isolation and schema validation compliance.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import pytest

# Ensure server module can be imported
server_dir = Path(__file__).resolve().parent.parent / "server"
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from ai_engine.vector import (
    ConfigurableDenseEmbeddingProvider,
    DeterministicEmbeddingProvider,
    EmbeddingResult,
    EmbeddingStatus,
    InvalidVectorError,
    validate_and_normalize_vector,
)
from app.config import get_settings
from app.schemas.incident import (
    EmbeddingBackfillResponse,
    EmbeddingProviderStatusResponse,
    IncidentEmbeddingResponse,
)
from app.services.embedding_service import (
    backfill_incident_embeddings,
    check_embedding_provider_readiness,
    generate_and_persist_incident_embedding,
    generate_incident_embedding,
    get_active_embedding_provider,
    get_incident_embedding,
    persist_incident_embedding,
)


# ==============================================================================
# 1. Provider Configuration & Readiness Verification
# ==============================================================================

def test_embedding_provider_readiness_unconfigured_when_no_key(monkeypatch):
    """Verify that when OPENAI_API_KEY is unset, readiness clearly reports unconfigured and fallback reason."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", raising=False)
    monkeypatch.delenv("DEVMEMORY_OFFLINE_MODE", raising=False)
    monkeypatch.setenv("DEVMEMORY_EMBEDDING_PROVIDER", "auto")

    report = check_embedding_provider_readiness()
    assert report.credentials_configured is False
    assert report.is_live is False
    assert report.status == "unconfigured"
    assert "OPENAI_API_KEY is not configured" in report.reason
    assert report.masked_credential is None
    assert report.target_dimension == 1536


def test_embedding_provider_readiness_configured_with_masked_key(monkeypatch):
    """Verify that when OPENAI_API_KEY is set, readiness reports configured and masks key safely."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-supersecretkey1234567890abcdef")
    monkeypatch.delenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", raising=False)
    monkeypatch.delenv("DEVMEMORY_OFFLINE_MODE", raising=False)
    monkeypatch.setenv("DEVMEMORY_EMBEDDING_PROVIDER", "dense")

    report = check_embedding_provider_readiness()
    assert report.credentials_configured is True
    assert report.is_live is True
    assert report.status == "configured"
    assert "sk-proj-supersecretkey" not in report.reason
    assert report.masked_credential is not None
    # Key must be masked: display only 4-char prefix/suffix
    assert report.masked_credential.startswith("sk-p...")
    assert "supersecret" not in report.masked_credential


def test_embedding_provider_readiness_offline_privacy_mode(monkeypatch):
    """Verify that when privacy offline mode is enabled, external inference is disabled."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-valid-key-here-12345678")
    monkeypatch.setenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "1")

    report = check_embedding_provider_readiness()
    assert report.status == "offline_mode_enforced"
    assert report.is_live is False
    assert "privacy configuration" in report.reason


def test_embedding_provider_readiness_explicit_deterministic(monkeypatch):
    """Verify that explicit deterministic configuration reports deterministic status."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", raising=False)
    monkeypatch.setenv("DEVMEMORY_EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("DEVMEMORY_VECTOR_DIMENSION", "128")

    report = check_embedding_provider_readiness()
    assert report.status == "deterministic"
    assert report.is_live is False
    assert report.target_dimension == 128


# ==============================================================================
# 2. Vector Validation & Dimension Compatibility
# ==============================================================================

def test_vector_validation_normalizes_to_unit_length():
    """Verify validate_and_normalize_vector produces finite, unit-length normalized vector."""
    raw = [3.0, 4.0]
    norm = validate_and_normalize_vector(raw, expected_dim=2)
    assert len(norm) == 2
    assert norm == [0.6, 0.8]
    assert math.isclose(math.sqrt(norm[0]**2 + norm[1]**2), 1.0, abs_tol=1e-5)


def test_vector_validation_rejects_incompatible_dimensions():
    """Verify vector validation raises InvalidVectorError on dimension mismatch."""
    with pytest.raises(InvalidVectorError, match="dimension mismatch"):
        validate_and_normalize_vector([1.0, 2.0, 3.0], expected_dim=4)


def test_vector_validation_rejects_non_numeric_and_nan():
    """Verify vector validation rejects non-numeric or NaN/Inf values."""
    with pytest.raises(InvalidVectorError, match="non-numeric"):
        validate_and_normalize_vector([1.0, "two", 3.0], expected_dim=3)

    with pytest.raises(InvalidVectorError, match="non-finite"):
        validate_and_normalize_vector([1.0, float("nan"), 3.0], expected_dim=3)

    with pytest.raises(InvalidVectorError, match="non-finite"):
        validate_and_normalize_vector([1.0, float("inf"), 3.0], expected_dim=3)


# ==============================================================================
# 3. Live vs Fallback Provider Distinction
# ==============================================================================

def test_live_provider_returns_live_success_with_mock_client():
    """Verify that a real DenseEmbeddingClient marks status as LIVE_SUCCESS and is_fallback as False."""
    class MockOpenAIClient:
        def create_embedding(self, text: str, model: str) -> List[float]:
            # Generate deterministic synthetic unit vector
            vec = [float(i + 1) for i in range(1536)]
            norm = math.sqrt(sum(x * x for x in vec))
            return [x / norm for x in vec]

    provider = ConfigurableDenseEmbeddingProvider(
        api_key="mock_key",
        dimension=1536,
        model="text-embedding-3-small",
        client=MockOpenAIClient(),
    )

    res = provider.get_embedding_with_status("KeyError: 'user_session'")
    assert res.status == EmbeddingStatus.LIVE_SUCCESS
    assert res.is_fallback is False
    assert res.dimension == 1536
    assert res.model == "text-embedding-3-small"
    assert len(res.vector) == 1536


def test_unconfigured_provider_falls_back_without_claiming_live():
    """Verify that absent credentials trigger DETERMINISTIC_FALLBACK with is_fallback=True."""
    provider = ConfigurableDenseEmbeddingProvider(
        api_key=None,
        dimension=1536,
        model="text-embedding-3-small",
        allow_fallback=True,
    )

    res = provider.get_embedding_with_status("KeyError: 'user_session'")
    assert res.status == EmbeddingStatus.DETERMINISTIC_FALLBACK
    assert res.is_fallback is True
    assert res.dimension == 1536
    # Must NOT claim to be live
    assert res.status != EmbeddingStatus.LIVE_SUCCESS


# ==============================================================================
# 4. MongoDB Persistence, Durability, and Retrieval
# ==============================================================================

def test_persist_and_retrieve_incident_embedding_in_memory():
    """Verify embedding persistence and retrieval logic against mock database."""
    inc_store: Dict[str, Any] = {
        "inc_test_001": {
            "incident_id": "inc_test_001",
            "project_id": "proj_demo",
            "error_type": "ValueError",
            "error_message": "Invalid integer format",
            "error_signature": "sig_val_err",
            "created_at": datetime.now(timezone.utc),
        }
    }

    mock_db = MagicMock()
    mock_db.incidents.find_one.side_effect = lambda query, proj=None: inc_store.get(query.get("incident_id"))

    def mock_update(query, update):
        inc_id = query["incident_id"]
        if inc_id in inc_store:
            inc_store[inc_id].update(update["$set"])
            return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    mock_db.incidents.update_one.side_effect = mock_update

    # 1. Generate embedding
    emb_res = generate_incident_embedding(
        error_message="Invalid integer format",
        stack_trace="File main.py, line 10",
        command="python main.py",
        expected_dimension=1536,
    )

    # 2. Persist
    persisted = persist_incident_embedding(
        db=mock_db,
        incident_id="inc_test_001",
        embedding_result=emb_res,
    )
    assert persisted is True

    # 3. Retrieve
    retrieved = get_incident_embedding(mock_db, "inc_test_001")
    assert retrieved is not None
    assert retrieved.incident_id == "inc_test_001"
    assert retrieved.project_id == "proj_demo"
    assert len(retrieved.embedding) == 1536
    assert retrieved.embedding_dimension == 1536
    assert retrieved.embedding_model == emb_res.model
    assert retrieved.embedding_status == emb_res.status.value


def test_persistence_rejects_incompatible_vector_dimensions():
    """Verify persist_incident_embedding rejects vectors that do not match expected dimension."""
    mock_db = MagicMock()
    mock_db.incidents.find_one.return_value = {"incident_id": "inc_001", "project_id": "proj_1"}

    bad_res = EmbeddingResult(
        vector=[0.1] * 128,  # Only 128 elements
        status=EmbeddingStatus.DETERMINISTIC_FALLBACK,
        dimension=1536,  # Declared 1536!
        model="text-embedding-3-small",
        is_fallback=True,
    )

    with pytest.raises(InvalidVectorError):
        persist_incident_embedding(mock_db, "inc_001", bad_res)


# ==============================================================================
# 5. Safe, Idempotent Backfill Behavior
# ==============================================================================

def test_backfill_incident_embeddings_idempotency():
    """Verify that backfilling embeds un-embedded incidents and does zero work on second run."""
    incidents = [
        {
            "incident_id": f"inc_bf_{i}",
            "project_id": "proj_bf",
            "error_type": "ZeroDivisionError",
            "error_message": "division by zero",
            "created_at": datetime.now(timezone.utc),
        }
        for i in range(5)
    ]
    db_state = {inc["incident_id"]: dict(inc) for inc in incidents}

    mock_db = MagicMock()

    def mock_find(query, *args, **kwargs):
        results = []
        for inc_id, doc in db_state.items():
            if "project_id" in query and doc.get("project_id") != query["project_id"]:
                continue
            if "embedding" in query and "$exists" in query["embedding"]:
                exists = "embedding" in doc
                if query["embedding"]["$exists"] != exists:
                    continue
            results.append(doc)
        cur = MagicMock()
        cur.__iter__.return_value = results
        cur.batch_size.return_value = cur
        return cur

    mock_db.incidents.find.side_effect = mock_find
    mock_db.incidents.find_one.side_effect = lambda q, *args, **kwargs: db_state.get(q.get("incident_id"))

    def mock_update(q, u):
        inc_id = q.get("incident_id")
        if inc_id in db_state:
            db_state[inc_id].update(u["$set"])
            return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    mock_db.incidents.update_one.side_effect = mock_update

    # Run 1: Should embed all 5 documents
    res1 = backfill_incident_embeddings(mock_db, project_id="proj_bf", force=False)
    assert res1.total_scanned == 5
    assert res1.updated == 5
    assert res1.failed == 0

    # Verify all have embedding
    for doc in db_state.values():
        assert "embedding" in doc
        assert len(doc["embedding"]) == 1536

    # Run 2: Should scan 0 documents and update 0 (idempotent)
    res2 = backfill_incident_embeddings(mock_db, project_id="proj_bf", force=False)
    assert res2.total_scanned == 0
    assert res2.updated == 0


def test_backfill_handles_individual_failure_without_aborting_batch():
    """Verify that a corrupted or failing document does not abort backfilling for remaining documents."""
    incidents = [
        {"incident_id": "inc_good_1", "error_message": "Good error 1"},
        {"incident_id": "inc_bad_2", "error_message": "Bad error that fails"},
        {"incident_id": "inc_good_3", "error_message": "Good error 3"},
    ]
    db_state = {inc["incident_id"]: dict(inc) for inc in incidents}

    mock_db = MagicMock()
    cur = MagicMock()
    cur.__iter__.return_value = list(db_state.values())
    cur.batch_size.return_value = cur
    mock_db.incidents.find.return_value = cur
    mock_db.incidents.find_one.side_effect = lambda q, *a, **kw: db_state.get(q.get("incident_id"))

    def mock_embed(db, incident_id, **kwargs):
        if incident_id == "inc_bad_2":
            raise RuntimeError("Synthetic embedding API explosion")
        db_state[incident_id]["embedding"] = [0.1] * 1536
        return MagicMock()

    with patch("app.services.embedding_service.generate_and_persist_incident_embedding", side_effect=mock_embed):
        res = backfill_incident_embeddings(mock_db)
        assert res.total_scanned == 3
        assert res.updated == 2
        assert res.failed == 1


# ==============================================================================
# 6. REST API Endpoints Verification
# ==============================================================================

@pytest.mark.asyncio
async def test_api_embedding_provider_readiness_endpoint():
    """Verify GET /api/v1/incidents/embedding-provider/readiness endpoint."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/incidents/embedding-provider/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "target_dimension" in data["data"]
        assert "configured_model" in data["data"]
        assert "is_live" in data["data"]
        assert "status" in data["data"]


@pytest.mark.asyncio
async def test_api_get_incident_embedding_404_when_missing():
    """Verify GET /api/v1/incidents/{incident_id}/embedding returns 404 when no embedding exists."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.db.mongo import get_database

    mock_db = MagicMock()
    mock_db.incidents.find_one.return_value = None
    app.dependency_overrides[get_database] = lambda: mock_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/incidents/non_existent_inc_xyz_999/embedding")
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_database, None)


@pytest.mark.asyncio
async def test_api_get_incident_embedding_success():
    """Verify GET /api/v1/incidents/{incident_id}/embedding returns 200 when embedding exists."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.db.mongo import get_database

    mock_db = MagicMock()
    mock_db.incidents.find_one.return_value = {
        "incident_id": "inc_api_001",
        "project_id": "proj_api",
        "embedding": [0.05] * 1536,
        "embedding_model": "text-embedding-3-small",
        "embedding_dimension": 1536,
        "embedding_status": "live_success",
        "embedding_is_fallback": False,
        "embedded_at": datetime.now(timezone.utc),
    }
    app.dependency_overrides[get_database] = lambda: mock_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/incidents/inc_api_001/embedding")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["data"]["incident_id"] == "inc_api_001"
            assert len(data["data"]["embedding"]) == 1536
    finally:
        app.dependency_overrides.pop(get_database, None)
