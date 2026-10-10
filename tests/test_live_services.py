"""
Tests for live external services (Groq LLM, OpenAI Embeddings, MongoDB Atlas).

Guarantees:
When credentials (GROQ_API_KEY, OPENAI_API_KEY, MONGODB_ATLAS_URI) are not configured
in the environment, tests explicitly report SKIPPED status rather than silently failing
or pretending to pass using mock data.
"""

import os
import pytest

from ai_engine.llm_client import GroqLLMClient
from ai_engine.vector import ConfigurableDenseEmbeddingProvider, MongoVectorSearchAdapter


@pytest.mark.skipif(
    not os.getenv("GROQ_API_KEY"),
    reason="GROQ_API_KEY not configured; skipping live Groq LLM inference test.",
)
def test_live_groq_llm_service():
    """Live integration test for Groq API."""
    client = GroqLLMClient()
    response = client.generate_diagnosis(
        system_prompt="You are an expert diagnostic assistant. Respond in valid JSON.",
        user_prompt="Explain KeyError: 'id'",
    )
    assert len(response) > 0


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not configured; skipping live OpenAI dense embedding test.",
)
def test_live_openai_dense_embedding_service():
    """Live integration test for OpenAI text-embedding-3-small."""
    provider = ConfigurableDenseEmbeddingProvider(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="text-embedding-3-small",
        dimension=1536,
    )
    vec = provider.get_embedding("KeyError: 'user_id' in session handler")
    assert len(vec) == 1536


@pytest.mark.skipif(
    not os.getenv("MONGODB_ATLAS_URI"),
    reason="MONGODB_ATLAS_URI not configured; skipping live Atlas $vectorSearch test.",
)
def test_live_mongo_atlas_vector_search():
    """Live integration test for MongoDB Atlas Vector Search."""
    adapter = MongoVectorSearchAdapter(
        connection_uri=os.getenv("MONGODB_ATLAS_URI"),
        index_name=os.getenv("MONGODB_VECTOR_INDEX", "incident_vector_index"),
    )
    # Search probe vector
    res = adapter.search_project_vectors(
        query_vector=[0.1] * 1536,
        project_id="proj_live_test",
    )
    assert isinstance(res, list)


def test_validate_live_provider_skipped_when_unconfigured(monkeypatch):
    """Verify that validate_live_embedding_provider cleanly reports SKIPPED when key is absent."""
    from ai_engine.validate_live_provider import validate_live_embedding_provider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report = validate_live_embedding_provider()

    assert report["status"] == "SKIPPED"
    assert report["ran_live"] is False
    assert report["credentials_configured"] is False
    assert report["configured_model"] == "text-embedding-3-small"
    assert report["target_dimension"] == 1536
    assert "OPENAI_API_KEY is not configured" in report["reason"]


def test_audit_atlas_vector_search_readiness_offline(monkeypatch):
    """Verify that Atlas audit validates pipeline structure offline without live Atlas cluster."""
    from ai_engine.validate_live_provider import audit_atlas_vector_search_readiness

    monkeypatch.delenv("MONGODB_ATLAS_URI", raising=False)
    report = audit_atlas_vector_search_readiness()

    assert report["pipeline_builder_status"] == "VALIDATED"
    assert report["status"] == "NOT EXERCISED"
    assert report["live_atlas_run"] is False
    assert report["configured_dimension"] == 1536


def test_offline_privacy_opt_out_embedding_provider(monkeypatch):
    """Verify that privacy opt-out bypasses external API calls even if API key is present."""
    from ai_engine.vector import ConfigurableDenseEmbeddingProvider, DeterministicEmbeddingProvider

    class NetworkSpyClient:
        def __init__(self):
            self.called = False

        def create_embedding(self, text: str, model: str):
            self.called = True
            return [1.0] * 1536

    spy = NetworkSpyClient()
    fallback = DeterministicEmbeddingProvider(dimension=128)
    provider = ConfigurableDenseEmbeddingProvider(
        api_key="sk-synthetic-test-key",
        dimension=128,
        client=spy,
        fallback_provider=fallback,
    )

    # 1. Without opt-out, client is called
    monkeypatch.delenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", raising=False)
    monkeypatch.delenv("DEVMEMORY_OFFLINE_MODE", raising=False)
    vec1 = provider.get_embedding("Test query")
    assert spy.called is True

    # 2. With DEV_MEMORY_DISABLE_EXTERNAL_AI="true", client is NEVER called
    spy.called = False
    monkeypatch.setenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "true")
    vec2 = provider.get_embedding("Test query")
    assert spy.called is False
    assert vec2 == fallback.get_embedding("Test query")

    # 3. With DEVMEMORY_OFFLINE_MODE="1", client is NEVER called
    monkeypatch.delenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", raising=False)
    monkeypatch.setenv("DEVMEMORY_OFFLINE_MODE", "1")
    vec3 = provider.get_embedding("Test query")
    assert spy.called is False
    assert vec3 == fallback.get_embedding("Test query")
