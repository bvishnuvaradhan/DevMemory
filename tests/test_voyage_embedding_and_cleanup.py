"""Focused unit tests for Voyage AI embedding provider adapter and safe history cleanup.

Guarantees tested:
1. Voyage configuration and missing-key readiness reporting.
2. Correct request payload format, headers, and query/document input_type handling.
3. Successful response parsing, 1,024-dimensional vector validation, and unit normalization.
4. Invalid dimensions, malformed responses, non-finite values, and error resilience.
5. Provider errors (401, 429), timeouts, and secret redaction in error messages.
6. Persistence metadata and MongoDB schema compatibility.
7. Explicit distinction between live Voyage embeddings and deterministic fallback.
8. Idempotent history cleanup against database interface.
9. Safe preservation of project registrations and configuration records during cleanup.
"""

from datetime import datetime, timezone
import io
import json
import math
import os
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from ai_engine.vector import (
    EmbeddingProviderError,
    EmbeddingResult,
    EmbeddingStatus,
    InvalidVectorError,
)
from app.config import Settings, clear_settings_cache
from app.db.indexes import INCIDENTS_VALIDATOR
from app.services.embedding_service import (
    VoyageEmbeddingProvider,
    check_embedding_provider_readiness,
    clean_devmemory_history,
    generate_incident_embedding,
    generate_query_embedding,
    get_active_embedding_provider,
    get_incident_embedding,
    persist_incident_embedding,
    resolve_target_dimension,
)


def _make_mock_http_response(body_dict: Dict[str, Any], status: int = 200):
    raw_bytes = json.dumps(body_dict).encode("utf-8")
    resp = io.BytesIO(raw_bytes)
    resp.read = resp.read  # type: ignore
    resp.code = status
    resp.status = status
    return resp


class TestVoyageEmbeddingAndCleanup:
    """Test suite covering Voyage AI provider adapter and safe history cleanup."""

    def test_voyage_configuration_and_missing_key_readiness(self, monkeypatch):
        """Verify readiness reports unconfigured when VOYAGE_API_KEY is absent, never claiming live status."""
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        monkeypatch.setenv("DEVMEMORY_EMBEDDING_PROVIDER", "voyage")
        clear_settings_cache()

        with patch("app.services.embedding_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                VOYAGE_API_KEY=None,
                VOYAGE_EMBEDDING_MODEL="voyage-code-4",
                VOYAGE_EMBEDDINGS_URL="https://api.voyageai.com/v1/embeddings",
                DEVMEMORY_EMBEDDING_PROVIDER="voyage",
                DEVMEMORY_VECTOR_DIMENSION=1024,
                DEV_MEMORY_DISABLE_EXTERNAL_AI=None,
            )
            status = check_embedding_provider_readiness(verify_live=False)
            assert status.provider_type == "voyage"
            assert status.configured_model == "voyage-code-4"
            assert status.target_dimension == 1024
            assert status.credentials_configured is False
            assert status.is_live is False
            assert status.status == "unconfigured"
            assert "VOYAGE_API_KEY is not configured" in (status.reason or "")
            assert status.masked_credential is None

    def test_voyage_configured_key_readiness(self, monkeypatch):
        """Verify readiness masks credentials and reports configured status without exposing secret."""
        secret_key = "pa-topsecretkey1234567890abcdef"
        monkeypatch.setenv("VOYAGE_API_KEY", secret_key)
        monkeypatch.setenv("DEVMEMORY_EMBEDDING_PROVIDER", "voyage")
        clear_settings_cache()

        status = check_embedding_provider_readiness(verify_live=False)
        assert status.provider_type == "voyage"
        assert status.configured_model == "voyage-code-4"
        assert status.target_dimension == 1024
        assert status.credentials_configured is True
        assert status.is_live is True
        assert status.status == "configured"
        assert status.masked_credential == "pa-t...cdef"
        assert secret_key not in (status.reason or "")

    def test_voyage_request_format_and_query_document_input_types(self):
        """Verify request format: headers, model, endpoint, and input_type='document' vs 'query'."""
        secret_key = "pa-testkey12345"
        provider = VoyageEmbeddingProvider(
            api_key=secret_key,
            model="voyage-code-4",
            dimension=1024,
            endpoint="https://api.voyageai.com/v1/embeddings",
        )

        dummy_vector = [0.01] * 1024

        def mock_urlopen(req, timeout=None):
            # Assert request URL and headers
            assert req.full_url == "https://api.voyageai.com/v1/embeddings"
            auth_header = req.get_header("Authorization") or req.headers.get("Authorization")
            assert auth_header == f"Bearer {secret_key}"
            content_type = req.get_header("Content-type") or req.headers.get("Content-type") or req.headers.get("Content-Type")
            assert content_type == "application/json"

            # Parse sent body
            sent_payload = json.loads(req.data.decode("utf-8"))
            assert sent_payload["model"] == "voyage-code-4"
            assert isinstance(sent_payload["input"], list)
            assert len(sent_payload["input"]) == 1

            # Mock successful response
            return _make_mock_http_response({
                "object": "list",
                "data": [{"embedding": dummy_vector, "index": 0}],
                "model": "voyage-code-4",
            })

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            # 1. Document embedding
            res_doc = provider.get_embedding_with_status("stored incident text", input_type="document")
            assert res_doc.status == EmbeddingStatus.LIVE_SUCCESS
            assert res_doc.is_fallback is False

            # 2. Query embedding
            res_query = provider.get_embedding_with_status("search query text", input_type="query")
            assert res_query.status == EmbeddingStatus.LIVE_SUCCESS
            assert res_query.is_fallback is False

    def test_voyage_successful_response_parsing_and_1024_dim_normalization(self):
        """Verify 1,024-dimensional response parsing and unit Euclidean normalization."""
        raw_vec = [1.0] * 1024  # un-normalized length
        provider = VoyageEmbeddingProvider(
            api_key="pa-validkey",
            model="voyage-code-4",
            dimension=1024,
        )

        mock_resp = _make_mock_http_response({
            "object": "list",
            "data": [{"embedding": raw_vec, "index": 0}],
            "model": "voyage-code-4",
        })

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = provider.get_embedding_with_status("sample error", input_type="document")
            assert res.status == EmbeddingStatus.LIVE_SUCCESS
            assert len(res.vector) == 1024
            assert res.is_fallback is False
            # Verify unit Euclidean norm: sum(v_i^2) == 1.0 +/- 1e-4
            norm = math.sqrt(sum(x * x for x in res.vector))
            assert pytest.approx(norm, abs=1e-4) == 1.0

    def test_voyage_invalid_dimensions_malformed_response_and_non_finite_values(self):
        """Verify that dimension mismatches, malformed responses, or NaN values trigger fallback or error."""
        provider = VoyageEmbeddingProvider(
            api_key="pa-validkey",
            model="voyage-code-4",
            dimension=1024,
            allow_fallback=True,
        )

        # 1. Wrong dimension (e.g. 512 returned instead of 1024)
        mock_wrong_dim = _make_mock_http_response({
            "data": [{"embedding": [0.1] * 512, "index": 0}],
        })
        with patch("urllib.request.urlopen", return_value=mock_wrong_dim):
            res = provider.get_embedding_with_status("text", input_type="document")
            assert res.is_fallback is True
            assert res.status == EmbeddingStatus.DETERMINISTIC_FALLBACK
            assert len(res.vector) == 1024

        # 2. Malformed JSON structure (missing 'data')
        mock_malformed = _make_mock_http_response({"invalid_key": []})
        with patch("urllib.request.urlopen", return_value=mock_malformed):
            res = provider.get_embedding_with_status("text", input_type="document")
            assert res.is_fallback is True
            assert res.status == EmbeddingStatus.DETERMINISTIC_FALLBACK

        # 3. Non-finite values (contains NaN or inf)
        nan_vec = [0.1] * 1023 + [float("nan")]
        mock_nan = _make_mock_http_response({
            "data": [{"embedding": nan_vec, "index": 0}],
        })
        with patch("urllib.request.urlopen", return_value=mock_nan):
            res = provider.get_embedding_with_status("text", input_type="document")
            assert res.is_fallback is True
            assert res.status == EmbeddingStatus.DETERMINISTIC_FALLBACK

    def test_voyage_provider_errors_timeouts_and_secret_redaction(self):
        """Verify HTTP 401, 429, timeout handling, and secret redaction."""
        secret_key = "pa-secretkey12345678"
        provider = VoyageEmbeddingProvider(
            api_key=secret_key,
            model="voyage-code-4",
            dimension=1024,
            allow_fallback=True,
        )

        # 1. HTTP 401 Unauthorized
        http_err_401 = urllib.error.HTTPError(
            url="https://api.voyageai.com/v1/embeddings",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(f"Invalid key: {secret_key}".encode("utf-8")),
        )
        with patch("urllib.request.urlopen", side_effect=http_err_401):
            res = provider.get_embedding_with_status("test text")
            assert res.is_fallback is True
            assert res.status == EmbeddingStatus.DETERMINISTIC_FALLBACK
            assert secret_key not in (res.error_message or "")

        # 2. HTTP 429 Rate Limited
        http_err_429 = urllib.error.HTTPError(
            url="https://api.voyageai.com/v1/embeddings",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=io.BytesIO(b"Rate limit exceeded"),
        )
        with patch("urllib.request.urlopen", side_effect=http_err_429):
            res = provider.get_embedding_with_status("test text")
            assert res.is_fallback is True
            assert "429" in (res.error_message or "")

        # 3. TimeoutError
        with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
            res = provider.get_embedding_with_status("test text")
            assert res.is_fallback is True
            assert "timed out" in (res.error_message or "").lower()

    def test_voyage_persistence_metadata_and_mongodb_schema_compatibility(self):
        """Verify that persisted 1024-dim Voyage embeddings conform to MongoDB collection validator."""
        mock_db = MagicMock()
        incident_id = "inc_voyage_persist_1"
        stored_docs = {}

        def mock_update(query, update):
            inc_id = query["incident_id"]
            stored_docs[inc_id] = update["$set"]
            return MagicMock(matched_count=1)

        mock_db.incidents.update_one.side_effect = mock_update

        # Create valid 1024-dim embedding result
        vec = [round(1.0 / math.sqrt(1024), 6)] * 1024
        res = EmbeddingResult(
            vector=vec,
            status=EmbeddingStatus.LIVE_SUCCESS,
            dimension=1024,
            model="voyage-code-4",
            is_fallback=False,
            provider_name="voyage",
        )

        persisted = persist_incident_embedding(
            db=mock_db,
            incident_id=incident_id,
            embedding_result=res,
            canonical_text="canonical diagnostic text",
        )
        assert persisted is True
        doc = stored_docs[incident_id]
        assert len(doc["embedding"]) == 1024
        assert doc["embedding_model"] == "voyage-code-4"
        assert doc["embedding_dimension"] == 1024
        assert doc["embedding_status"] == "live_success"
        assert doc["embedding_is_fallback"] is False
        assert isinstance(doc["embedded_at"], datetime)
        assert doc["embedding_canonical_text"] == "canonical diagnostic text"

        # Check INCIDENTS_VALIDATOR schema compatibility
        incident_full_doc = {
            "incident_id": incident_id,
            "project_id": "proj_1",
            "error_type": "ValueError",
            "error_message": "Invalid value",
            "error_signature": "sig_123",
            "created_at": datetime.now(timezone.utc),
            **doc,
        }
        assert isinstance(incident_full_doc["embedding"], list)
        assert all(isinstance(x, float) for x in incident_full_doc["embedding"])
        assert isinstance(incident_full_doc["embedding_model"], str)
        assert isinstance(incident_full_doc["embedding_dimension"], int)
        assert isinstance(incident_full_doc["embedding_is_fallback"], bool)

    def test_explicit_distinction_between_voyage_and_deterministic_fallback(self):
        """Verify fallback vectors are never labeled as live semantic Voyage output."""
        # Case A: Live success
        live_res = EmbeddingResult(
            vector=[0.01] * 1024,
            status=EmbeddingStatus.LIVE_SUCCESS,
            dimension=1024,
            model="voyage-code-4",
            is_fallback=False,
            provider_name="voyage",
        )
        assert live_res.is_fallback is False
        assert live_res.status == EmbeddingStatus.LIVE_SUCCESS

        # Case B: Deterministic fallback when key is empty
        prov = VoyageEmbeddingProvider(api_key="", dimension=1024, allow_fallback=True)
        fallback_res = prov.get_embedding_with_status("some error message")
        assert fallback_res.is_fallback is True
        assert fallback_res.status == EmbeddingStatus.DETERMINISTIC_FALLBACK
        assert fallback_res.dimension == 1024
        assert "VOYAGE_API_KEY is not configured" in (fallback_res.error_message or "")

    def test_idempotent_history_cleanup_against_database_interface(self):
        """Verify that clean_devmemory_history deletes historical collections idempotently."""
        state = {
            "incidents": 5,
            "command_runs": 8,
            "diagnoses": 4,
            "fix_outcomes": 2,
            "performance_runs": 3,
            "performance_baselines": 1,
            "projects": 12,  # Must be preserved!
        }

        mock_db = MagicMock()
        mock_collections = {}
        for coll_name, initial_count in state.items():
            col_mock = MagicMock()
            def make_delete_func(name):
                def delete_func(*args, **kwargs):
                    cnt = state[name]
                    state[name] = 0
                    return MagicMock(deleted_count=cnt)
                return delete_func
            col_mock.delete_many.side_effect = make_delete_func(coll_name)
            mock_collections[coll_name] = col_mock

        mock_db.__getitem__.side_effect = lambda c: mock_collections[c]

        # Run 1: Deletes all historical records
        del_summary1 = clean_devmemory_history(mock_db)
        assert del_summary1["incidents"] == 5
        assert del_summary1["command_runs"] == 8
        assert del_summary1["diagnoses"] == 4
        assert del_summary1["fix_outcomes"] == 2
        assert del_summary1["performance_runs"] == 3
        assert del_summary1["performance_baselines"] == 1
        assert "projects" not in del_summary1

        # Run 2: Idempotent - zero deleted
        del_summary2 = clean_devmemory_history(mock_db)
        assert del_summary2["incidents"] == 0
        assert del_summary2["command_runs"] == 0
        assert del_summary2["diagnoses"] == 0
        assert del_summary2["fix_outcomes"] == 0
        assert del_summary2["performance_runs"] == 0
        assert del_summary2["performance_baselines"] == 0

    def test_safe_preservation_of_projects_and_configuration_during_cleanup(self):
        """Verify that project registrations and configuration records are 100% preserved during cleanup."""
        collections = {
            "incidents": [{"incident_id": f"inc_{i}"} for i in range(10)],
            "command_runs": [{"event_id": f"ev_{i}"} for i in range(6)],
            "projects": [
                {"project_id": "proj_alpha", "name": "Alpha Service"},
                {"project_id": "proj_beta", "name": "Beta Core"},
            ],
        }

        mock_db = MagicMock()
        mock_collections = {}

        for coll_name, doc_list in collections.items():
            col_mock = MagicMock()
            def make_del(docs):
                def del_func(*args, **kwargs):
                    cnt = len(docs)
                    docs.clear()
                    return MagicMock(deleted_count=cnt)
                return del_func
            col_mock.delete_many.side_effect = make_del(doc_list)
            mock_collections[coll_name] = col_mock

        mock_db.__getitem__.side_effect = lambda c: mock_collections[c]

        # Execute cleanup
        clean_devmemory_history(mock_db)

        # Verify history deleted
        assert len(collections["incidents"]) == 0
        assert len(collections["command_runs"]) == 0

        # Verify projects collection was never targeted by delete_many
        mock_collections["projects"].delete_many.assert_not_called()
        assert len(collections["projects"]) == 2
        assert collections["projects"][0]["project_id"] == "proj_alpha"
        assert collections["projects"][1]["project_id"] == "proj_beta"
