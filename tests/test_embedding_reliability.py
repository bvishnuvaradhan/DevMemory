"""Tests for Phase 6.5 Embedding Provider Reliability and Failure-Path Hardening.

Verifies:
1. Provider response validation:
   - Empty responses, missing/malformed fields, unexpected dimensions
   - Non-numeric, NaN, infinite, boolean vector values
   - Unexpected model response structures
   - Timeouts, HTTP errors (429 rate limit, 500 server error), connection failures
   - Invalid configuration & unsupported model/dimension combinations
   - Corrupt vector rejection in MockVectorSearchAdapter & MongoVectorSearchAdapter
2. Deterministic fallback behavior:
   - Valid deterministic embeddings when fallback is permitted
   - Never presenting fallback as successful live embedding
   - Distinction between live success, fallback, opt-out, and unavailable failure
   - Failing closed when allow_fallback=False
   - Failing closed on dimension mismatch between dense and fallback provider
   - Sanitized exception logs without credential leakage
3. Privacy and offline guarantees:
   - Verification 1: External inference disabled means no outbound provider request
   - Verification 2: Offline mode works even when provider configuration is present
   - Verification 3: Synthetic test inputs are sanitized before external inference
   - Verification 4: Provider exceptions cannot expose API keys or sensitive payloads
   - Verification 5: Cross-project authorization remains independent of embedding similarity
   - Verification 6: Private incident data cannot become accessible through fallback or retrieval
   - Verification 7: Existing deterministic retrieval works without external credentials
"""

import math
import os
import urllib.error
from typing import Any, Dict, List, Optional
import pytest

from ai_engine.schemas import DiagnosisRequest, FixVerificationStatus
from ai_engine.privacy import redact_secrets, sanitize_file_path
from ai_engine.vector import (
    ConfigurableDenseEmbeddingProvider,
    DeterministicEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingResult,
    EmbeddingStatus,
    InvalidConfigurationError,
    InvalidVectorError,
    MockVectorSearchAdapter,
    MongoVectorSearchAdapter,
    cosine_similarity,
    get_configured_embedding_provider,
    validate_and_normalize_vector,
    validate_model_configuration,
)
from ai_engine.retrieval import (
    AuthorizationContext,
    InMemoryIncidentRepository,
    retrieve_memory,
)


class MockFlakyClient:
    """Mock client capable of simulating various provider failure modes."""

    def __init__(self, mode: str, dimension: int = 1536) -> None:
        self.mode = mode
        self.dimension = dimension
        self.call_count = 0
        self.received_texts: List[str] = []

    def create_embedding(self, text: str, model: str) -> Any:
        self.call_count += 1
        self.received_texts.append(text)

        if self.mode == "success":
            # Normal unit vector
            vec = [1.0] + [0.0] * (self.dimension - 1)
            return vec
        elif self.mode == "empty":
            return []
        elif self.mode == "none":
            return None
        elif self.mode == "wrong_dim":
            return [0.1] * (self.dimension // 2)
        elif self.mode == "nan":
            return [float("nan")] * self.dimension
        elif self.mode == "inf":
            return [float("inf")] * self.dimension
        elif self.mode == "non_numeric":
            return ["0.1", "0.2"] + [0.0] * (self.dimension - 2)
        elif self.mode == "boolean":
            return [True, False] + [0.0] * (self.dimension - 2)
        elif self.mode == "zero_magnitude":
            return [0.0] * self.dimension
        elif self.mode == "timeout":
            raise TimeoutError("Simulated client timeout after 5.0s")
        elif self.mode == "rate_limit":
            raise urllib.error.HTTPError(
                url="https://api.openai.com/v1/embeddings",
                code=429,
                msg="Too Many Requests",
                hdrs={},
                fp=None,
            )
        elif self.mode == "server_error":
            raise urllib.error.HTTPError(
                url="https://api.openai.com/v1/embeddings",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=None,
            )
        elif self.mode == "connection_refused":
            raise urllib.error.URLError("Connection refused by remote host")
        else:
            raise ValueError(f"Unknown mock mode: {self.mode}")


# ==============================================================================
# Task 2: Provider Response Validation Tests
# ==============================================================================

def test_validate_and_normalize_vector_invalid_inputs():
    """Verify vector validator rejects None, non-list, wrong dim, non-numeric, and non-finite."""
    # 1. None
    with pytest.raises(InvalidVectorError, match="Vector cannot be None"):
        validate_and_normalize_vector(None, expected_dim=4)

    # 2. Non-list
    with pytest.raises(InvalidVectorError, match="must be a list or tuple"):
        validate_and_normalize_vector("not_a_vector", expected_dim=4)

    # 3. Dimension mismatch
    with pytest.raises(InvalidVectorError, match="Vector dimension mismatch"):
        validate_and_normalize_vector([1.0, 0.0], expected_dim=4)

    # 4. Non-numeric element (string)
    with pytest.raises(InvalidVectorError, match="non-numeric"):
        validate_and_normalize_vector([1.0, "0.5", 0.0, 0.0], expected_dim=4)

    # 5. Non-numeric element (bool)
    with pytest.raises(InvalidVectorError, match="non-numeric"):
        validate_and_normalize_vector([True, 0.0, 0.0, 0.0], expected_dim=4)

    # 6. Non-finite element (NaN)
    with pytest.raises(InvalidVectorError, match="non-finite"):
        validate_and_normalize_vector([float("nan"), 0.0, 0.0, 0.0], expected_dim=4)

    # 7. Non-finite element (Inf)
    with pytest.raises(InvalidVectorError, match="non-finite"):
        validate_and_normalize_vector([float("inf"), 0.0, 0.0, 0.0], expected_dim=4)

    # 8. All zeros when allow_zero=False
    with pytest.raises(InvalidVectorError, match="Vector magnitude is zero"):
        validate_and_normalize_vector([0.0, 0.0, 0.0, 0.0], expected_dim=4, allow_zero=False)

    # 9. All zeros when allow_zero=True returns zero vector
    assert validate_and_normalize_vector([0.0, 0.0, 0.0, 0.0], expected_dim=4, allow_zero=True) == [0.0, 0.0, 0.0, 0.0]


def test_validate_model_configuration():
    """Verify configuration validator enforces model bounds and positive dimensions."""
    # Empty model name
    with pytest.raises(InvalidConfigurationError, match="cannot be empty"):
        validate_model_configuration("", dimension=1536)

    # Non-positive dimension
    with pytest.raises(InvalidConfigurationError, match="positive integer"):
        validate_model_configuration("text-embedding-3-small", dimension=0)
    with pytest.raises(InvalidConfigurationError, match="positive integer"):
        validate_model_configuration("text-embedding-3-small", dimension=-10)

    # ada-002 requires fixed 1536
    with pytest.raises(InvalidConfigurationError, match="fixed dimension is 1536"):
        validate_model_configuration("text-embedding-ada-002", dimension=512)
    validate_model_configuration("text-embedding-ada-002", dimension=1536)

    # text-embedding-3-small max dimension is 1536
    with pytest.raises(InvalidConfigurationError, match="maximum dimension is 1536"):
        validate_model_configuration("text-embedding-3-small", dimension=2048)
    validate_model_configuration("text-embedding-3-small", dimension=512)

    # text-embedding-3-large max dimension is 3072
    with pytest.raises(InvalidConfigurationError, match="maximum dimension is 3072"):
        validate_model_configuration("text-embedding-3-large", dimension=4096)
    validate_model_configuration("text-embedding-3-large", dimension=3072)


def test_provider_client_failure_modes_trigger_fallback():
    """Verify that malformed client responses trigger deterministic fallback rather than crashing."""
    failure_modes = [
        "empty",
        "none",
        "wrong_dim",
        "nan",
        "inf",
        "non_numeric",
        "boolean",
        "zero_magnitude",
        "timeout",
        "rate_limit",
        "server_error",
        "connection_refused",
    ]

    for mode in failure_modes:
        client = MockFlakyClient(mode=mode, dimension=128)
        fallback = DeterministicEmbeddingProvider(dimension=128)
        provider = ConfigurableDenseEmbeddingProvider(
            dimension=128,
            client=client,
            fallback_provider=fallback,
            allow_fallback=True,
        )

        res = provider.get_embedding_with_status("Database connection failed")
        assert res.status == EmbeddingStatus.DETERMINISTIC_FALLBACK, f"Mode {mode} failed to trigger fallback"
        assert res.is_fallback is True
        assert len(res.vector) == 128
        assert res.vector == fallback.get_embedding("Database connection failed")
        assert provider.last_status == EmbeddingStatus.DETERMINISTIC_FALLBACK


def test_vector_search_adapters_reject_corrupt_vectors():
    """Verify that corrupt vectors never silently enter vector store or distort ranking."""
    mock_adapter = MockVectorSearchAdapter(embedding_provider=DeterministicEmbeddingProvider(dimension=128))

    # Reject non-numeric or non-finite vector insertion
    with pytest.raises(InvalidVectorError):
        mock_adapter.add_incident({"incident_id": "bad1"}, embedding=[float("nan")] * 128)

    with pytest.raises(InvalidVectorError):
        mock_adapter.add_incident({"incident_id": "bad2"}, embedding=["0.1"] * 128)

    # Search with NaN query vector returns empty list cleanly
    res_nan = mock_adapter.search_project_vectors([float("nan")] * 128, project_id="proj_1")
    assert res_nan == []

    # Search with all-zero query vector returns empty list cleanly
    res_zero = mock_adapter.search_project_vectors([0.0] * 128, project_id="proj_1")
    assert res_zero == []

    # MongoVectorSearchAdapter also rejects NaN and all-zero query vectors safely offline
    mongo_adapter = MongoVectorSearchAdapter()
    assert mongo_adapter.search_project_vectors([float("nan")] * 128, project_id="proj_1") == []
    assert mongo_adapter.search_project_vectors([0.0] * 128, project_id="proj_1") == []


# ==============================================================================
# Task 3: Deterministic Fallback Behavior Tests
# ==============================================================================

def test_fallback_disabled_fails_closed():
    """Verify that when allow_fallback=False, client/network errors raise EmbeddingProviderError."""
    failing_client = MockFlakyClient(mode="timeout", dimension=128)
    provider = ConfigurableDenseEmbeddingProvider(
        dimension=128,
        client=failing_client,
        allow_fallback=False,
    )

    with pytest.raises(EmbeddingProviderError, match="fallback is disabled"):
        provider.get_embedding("Test failure")

    assert provider.last_status == EmbeddingStatus.UNAVAILABLE_FAILURE
    assert provider.last_result.is_fallback is False


def test_fallback_dimension_mismatch_fails_closed():
    """Verify that if fallback provider has different dimension, system fails closed."""
    failing_client = MockFlakyClient(mode="timeout", dimension=1536)
    # Fallback provider has 128 dimensions, but dense provider expects 1536
    mismatched_fallback = DeterministicEmbeddingProvider(dimension=128)
    provider = ConfigurableDenseEmbeddingProvider(
        dimension=1536,
        client=failing_client,
        fallback_provider=mismatched_fallback,
        allow_fallback=True,
    )

    with pytest.raises(EmbeddingProviderError, match="dimension .* does not match required"):
        provider.get_embedding("Test mismatch")

    assert provider.last_status == EmbeddingStatus.UNAVAILABLE_FAILURE


def test_callers_can_distinguish_provenance():
    """Verify callers can distinguish live success from fallback and offline opt-out."""
    success_client = MockFlakyClient(mode="success", dimension=128)
    timeout_client = MockFlakyClient(mode="timeout", dimension=128)
    fallback = DeterministicEmbeddingProvider(dimension=128)

    p_success = ConfigurableDenseEmbeddingProvider(dimension=128, client=success_client)
    p_fallback = ConfigurableDenseEmbeddingProvider(dimension=128, client=timeout_client, fallback_provider=fallback)

    # 1. Live success
    res1 = p_success.get_embedding_with_status("Query 1")
    assert res1.status == EmbeddingStatus.LIVE_SUCCESS
    assert res1.is_fallback is False
    assert p_success.last_status == EmbeddingStatus.LIVE_SUCCESS

    # 2. Fallback
    res2 = p_fallback.get_embedding_with_status("Query 2")
    assert res2.status == EmbeddingStatus.DETERMINISTIC_FALLBACK
    assert res2.is_fallback is True
    assert p_fallback.last_status == EmbeddingStatus.DETERMINISTIC_FALLBACK


# ==============================================================================
# Task 4: Privacy and Offline Guarantees Tests
# ==============================================================================

def test_privacy_guarantee_1_external_inference_disabled(monkeypatch):
    """Verification 1: DEV_MEMORY_DISABLE_EXTERNAL_AI disables outbound request."""
    client = MockFlakyClient(mode="success", dimension=128)
    provider = ConfigurableDenseEmbeddingProvider(dimension=128, client=client)

    monkeypatch.setenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "true")
    res = provider.get_embedding_with_status("Secret query")

    assert client.call_count == 0, "Outbound request made while external AI disabled!"
    assert res.status == EmbeddingStatus.OFFLINE_OPT_OUT
    assert res.is_fallback is True


def test_privacy_guarantee_2_offline_mode_with_credentials(monkeypatch):
    """Verification 2: DEVMEMORY_OFFLINE_MODE works even if credentials are present."""
    client = MockFlakyClient(mode="success", dimension=128)
    provider = ConfigurableDenseEmbeddingProvider(
        api_key="sk-synthetic-live-credential-should-not-be-used",
        dimension=128,
        client=client,
    )

    monkeypatch.setenv("DEVMEMORY_OFFLINE_MODE", "1")
    res = provider.get_embedding_with_status("Local error query")

    assert client.call_count == 0
    assert res.status == EmbeddingStatus.OFFLINE_OPT_OUT


def test_privacy_guarantee_3_synthetic_inputs_sanitized_before_inference():
    """Verification 3: Diagnostic text is scrubbed for secrets and paths before reaching client."""
    client = MockFlakyClient(mode="success", dimension=128)
    provider = ConfigurableDenseEmbeddingProvider(dimension=128, client=client)

    raw_token = "ghp_" + ("a" * 36)
    raw_query = f"GitHub API error with token {raw_token} in /Users/boga/code/repo/api.py"

    provider.get_embedding(raw_query)

    assert len(client.received_texts) == 1
    sent_text = client.received_texts[0]
    assert raw_token not in sent_text
    assert "[REDACTED_GITHUB_TOKEN]" in sent_text
    assert "/Users/boga" not in sent_text
    assert "~/code/repo/api.py" in sent_text


def test_privacy_guarantee_4_provider_exceptions_redact_secrets(caplog):
    """Verification 4: Provider error logs and exception messages never leak credentials."""
    import logging

    fake_secret = "-".join(["sk-proj", "abcdef1234567890abcdef1234567890"])

    class KeyLeakingClient:
        def create_embedding(self, text: str, model: str):
            raise RuntimeError(f"Connection refused to OpenAI with auth header Bearer {fake_secret}")

    provider = ConfigurableDenseEmbeddingProvider(
        dimension=128,
        client=KeyLeakingClient(),
        allow_fallback=True,
    )

    with caplog.at_level(logging.WARNING):
        res = provider.get_embedding_with_status("Some query")

    assert res.status == EmbeddingStatus.DETERMINISTIC_FALLBACK
    # Assert log message redacted the secret
    assert fake_secret not in caplog.text
    assert "[REDACTED_API_KEY]" in caplog.text or "[REDACTED" in caplog.text


def test_privacy_guarantee_5_cross_project_authorization_independent_of_similarity():
    """Verification 5: High embedding similarity cannot grant cross-project access without server authorization."""
    det_prov = DeterministicEmbeddingProvider(dimension=128)
    adapter = MockVectorSearchAdapter(embedding_provider=det_prov)

    # Cross-project incident from another project
    inc_other = {
        "incident_id": "inc_other_1",
        "project_id": "proj_other",
        "error_message": "ExactSameError: duplicate key in database table",
        "command": "python script.py",
        "resolution_summary": "Run migration script.",
        "is_public": True,
        "verification_status": FixVerificationStatus.VERIFIED,
    }
    repo = InMemoryIncidentRepository([inc_other])
    adapter.add_incident(inc_other)

    req = DiagnosisRequest(
        event_id="ev_test",
        project_id="proj_my_app",
        command="python script.py",
        exit_code=1,
        error_message="ExactSameError: duplicate key in database table",
    )

    # 1. Without server cross-project read authorization
    auth_denied = AuthorizationContext(
        user_id="user_1",
        project_id="proj_my_app",
        has_project_access=True,
        has_cross_project_read=False,  # DENIED
    )
    res_denied = retrieve_memory(
        req,
        auth_denied,
        repository=repo,
        vector_adapter=adapter,
        embedding_provider=det_prov,
        threshold=0.30,
    )
    assert len(res_denied.cross_project_matches) == 0, "Unauthorized cross-project precedent leaked!"

    # 2. With server cross-project read authorization
    auth_allowed = AuthorizationContext(
        user_id="user_1",
        project_id="proj_my_app",
        has_project_access=True,
        has_cross_project_read=True,  # AUTHORIZED
    )
    res_allowed = retrieve_memory(
        req,
        auth_allowed,
        repository=repo,
        vector_adapter=adapter,
        embedding_provider=det_prov,
        threshold=0.30,
    )
    assert len(res_allowed.cross_project_matches) == 1
    assert res_allowed.cross_project_matches[0].incident_id == "inc_other_1"


def test_privacy_guarantee_6_private_incident_data_never_disclosed_cross_project():
    """Verification 6: Private incident data (is_public=False) never leaks cross-project."""
    det_prov = DeterministicEmbeddingProvider(dimension=128)
    adapter = MockVectorSearchAdapter(embedding_provider=det_prov)

    inc_private = {
        "incident_id": "inc_private_secret",
        "project_id": "proj_other",
        "error_message": "DatabaseAuthFailed: invalid credentials",
        "resolution_summary": "Fixed connection string password.",
        "is_public": False,  # STRICTLY PRIVATE
    }
    repo = InMemoryIncidentRepository([inc_private])
    adapter.add_incident(inc_private)

    req = DiagnosisRequest(
        event_id="ev_priv",
        project_id="proj_my_app",
        command="python script.py",
        exit_code=1,
        error_message="DatabaseAuthFailed: invalid credentials",
    )
    auth = AuthorizationContext(
        user_id="user_1",
        project_id="proj_my_app",
        has_project_access=True,
        has_cross_project_read=True,
    )

    res = retrieve_memory(
        req,
        auth,
        repository=repo,
        vector_adapter=adapter,
        embedding_provider=det_prov,
        threshold=0.20,
    )
    assert len(res.cross_project_matches) == 0, "Private incident was disclosed cross-project!"


def test_privacy_guarantee_7_deterministic_retrieval_works_offline(monkeypatch):
    """Verification 7: Deterministic retrieval operates 100% offline without API keys."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("MONGODB_ATLAS_URI", raising=False)

    provider = get_configured_embedding_provider()
    assert isinstance(provider, DeterministicEmbeddingProvider)

    vec = provider.get_embedding("Offline deterministic error vector")
    assert len(vec) == 128
    assert math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, rel_tol=1e-3)
