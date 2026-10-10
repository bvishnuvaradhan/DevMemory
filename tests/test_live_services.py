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
        index_name=os.getenv("MONGODB_VECTOR_INDEX", "vector_index"),
    )
    # Search dummy vector
    res = adapter.search_project_vectors(
        query_vector=[0.1] * 1536,
        project_id="proj_live_test",
    )
    assert isinstance(res, list)
