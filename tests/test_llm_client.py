"""Tests for LLM clients in ai_engine.llm_client."""

import json
import pytest

from ai_engine.llm_client import GroqLLMClient, MockLLMClient


def test_mock_llm_client_default_response():
    """Mock client generates valid structured JSON containing the prompt event_id."""
    client = MockLLMClient()
    sys_prompt = "You are a diagnosis assistant"
    user_prompt = "Event ID: evt_test_123\nError: TypeError"

    response_str = client.generate_diagnosis(sys_prompt, user_prompt)
    data = json.loads(response_str)

    assert data["event_id"] == "evt_test_123"
    assert "summary" in data
    assert "likely_cause" in data
    assert "evidence" in data
    assert "hypotheses" in data
    assert "recommended_steps" in data
    assert data["fix_status"] == "unverified"


def test_mock_llm_client_custom_response():
    """Mock client returns custom string if provided."""
    custom = json.dumps({"custom": "data"})
    client = MockLLMClient(custom_response=custom)
    assert client.generate_diagnosis("sys", "user") == custom


def test_groq_client_requires_api_key(monkeypatch):
    """Groq client raises ValueError when GROQ_API_KEY is not set."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    client = GroqLLMClient(api_key=None)

    with pytest.raises(ValueError, match="GROQ_API_KEY environment variable is not set"):
        client.generate_diagnosis("sys", "user")


def test_groq_client_configuration(monkeypatch):
    """Groq client respects model and timeout settings."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_syntheticKeyForTestingOnly1234567890abcdef")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("GROQ_TIMEOUT_SECONDS", "15.0")

    client = GroqLLMClient()
    assert client.model == "llama-3.1-8b-instant"
    assert client.timeout_seconds == 15.0
    assert client.api_key == "gsk_syntheticKeyForTestingOnly1234567890abcdef"
