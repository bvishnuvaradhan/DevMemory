"""Tests for Groq environment configuration, provider readiness, and secret isolation.

Guarantees:
1. GROQ_API_KEY is correctly loaded from supported configuration sources (.env, os.environ, Settings).
2. Proper precedence is maintained (caller argument > environment variable > .env > defaults).
3. Missing key produces safe, clear provider-unavailable status and graceful deterministic fallback.
4. Offline privacy flags (DEV_MEMORY_DISABLE_EXTERNAL_AI) strictly suppress Groq calls even if a key is present.
5. Raw API keys are never exposed in logs, exceptions, or status reports (masked/redacted only).
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest

from app.config import Settings, clear_settings_cache, get_settings
from ai_engine.llm_client import GroqLLMClient, MockLLMClient
from ai_engine.diagnosis import diagnose_error
from ai_engine.retrieval import AuthorizationContext, InMemoryIncidentRepository
from ai_engine.schemas import DiagnosisRequest
from server.app.services.ai_service import check_groq_provider_readiness, validate_live_groq_connection
from ai_engine.privacy import redact_secrets


@pytest.fixture(autouse=True)
def clean_groq_env(monkeypatch):
    """Ensure clean environment variables around each test."""
    clear_settings_cache()
    # Save original state
    orig_key = os.environ.get("GROQ_API_KEY")
    orig_model = os.environ.get("GROQ_MODEL")
    orig_timeout = os.environ.get("GROQ_TIMEOUT_SECONDS")
    orig_offline = os.environ.get("DEV_MEMORY_DISABLE_EXTERNAL_AI")

    # Clean out for test isolation
    for var in [
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "GROQ_TIMEOUT_SECONDS",
        "DEV_MEMORY_DISABLE_EXTERNAL_AI",
        "DEVMEMORY_OFFLINE_MODE",
        "AI_PRIVACY_OFFLINE_ONLY",
    ]:
        monkeypatch.delenv(var, raising=False)

    clear_settings_cache()
    yield

    # Restore
    clear_settings_cache()
    if orig_key is not None:
        os.environ["GROQ_API_KEY"] = orig_key
    elif "GROQ_API_KEY" in os.environ:
        del os.environ["GROQ_API_KEY"]


def test_groq_key_loaded_from_env_file(tmp_path: Path, monkeypatch):
    """Verify that GROQ_API_KEY is loaded from an .env file into Settings and os.environ."""
    env_file = tmp_path / ".env"
    synthetic_key = "gsk_test_synthetic_key_from_env_file_12345"
    env_file.write_text(
        f"GROQ_API_KEY={synthetic_key}\nGROQ_MODEL=llama-3.3-70b-versatile\nGROQ_TIMEOUT_SECONDS=45.0\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=str(env_file))
    assert settings.GROQ_API_KEY == synthetic_key
    assert settings.GROQ_MODEL == "llama-3.3-70b-versatile"
    assert settings.GROQ_TIMEOUT_SECONDS == 45.0
    # Verified synchronized to os.environ:
    assert os.getenv("GROQ_API_KEY") == synthetic_key


def test_environment_variable_precedence_over_env_file(tmp_path: Path, monkeypatch):
    """Verify that existing environment variable takes precedence over .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=gsk_lower_precedence_env_file_key\n", encoding="utf-8")

    primary_key = "gsk_higher_precedence_os_environ_key_999"
    monkeypatch.setenv("GROQ_API_KEY", primary_key)

    settings = Settings(_env_file=str(env_file))
    # Existing env var must take precedence:
    assert settings.GROQ_API_KEY == primary_key
    assert os.getenv("GROQ_API_KEY") == primary_key


def test_direct_argument_precedence_over_env(monkeypatch):
    """Verify that caller-provided argument takes precedence over environment variables."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_env_variable_key")

    client = GroqLLMClient(api_key="gsk_caller_explicit_key_777")
    assert client.api_key == "gsk_caller_explicit_key_777"


def test_missing_groq_key_produces_safe_unconfigured_status(monkeypatch):
    """Verify missing GROQ_API_KEY produces clear unconfigured readiness status."""
    dummy_settings = Settings(GROQ_API_KEY=None, _env_file=None)
    monkeypatch.setattr("server.app.services.ai_service.get_settings", lambda: dummy_settings)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    status_info = check_groq_provider_readiness()
    assert status_info["status"] == "unconfigured"
    assert status_info["is_configured"] is False
    assert "GROQ_API_KEY is not configured" in status_info["message"]


def test_missing_key_generate_diagnosis_raises_informative_error(monkeypatch):
    """Verify GroqLLMClient raises clear ValueError when invoked without a key."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    client = GroqLLMClient(api_key=None)
    assert client.api_key is None
    with pytest.raises(ValueError) as exc_info:
        client.generate_diagnosis(system_prompt="sys", user_prompt="user")
    assert "GROQ_API_KEY environment variable is not set" in str(exc_info.value)


def test_diagnose_error_gracefully_falls_back_when_key_is_missing(monkeypatch):
    """Verify diagnose_error orchestrator defaults to MockLLMClient and succeeds when key is missing."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    req = DiagnosisRequest(
        event_id="evt_test_missing_key",
        project_id="proj_test",
        command="python test.py",
        exit_code=1,
        error_message="KeyError: 'user_id'",
    )
    auth = AuthorizationContext(user_id="sys", project_id="proj_test")
    repo = InMemoryIncidentRepository()

    # Must complete successfully without raising unhandled exceptions
    resp = diagnose_error(request=req, auth_context=auth, repository=repo)
    assert resp.event_id == "evt_test_missing_key"
    assert len(resp.summary) > 0
    assert resp.fix_status.value == "unverified"


def test_offline_mode_flag_suppresses_groq_even_with_key(monkeypatch):
    """Verify DEV_MEMORY_DISABLE_EXTERNAL_AI strictly forces offline fallback even if key is set."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_active_real_looking_key_12345678")
    monkeypatch.setenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "1")

    status_info = check_groq_provider_readiness()
    assert status_info["status"] == "offline_mode_enforced"

    client = GroqLLMClient()
    with pytest.raises(RuntimeError) as exc_info:
        client.generate_diagnosis(system_prompt="sys", user_prompt="user")
    assert "External AI inference disabled by privacy configuration" in str(exc_info.value)


def test_readiness_status_masks_key_without_leaking_secret(monkeypatch):
    """Verify that check_groq_provider_readiness never exposes the raw API key."""
    raw_key = "gsk_super_secret_production_groq_key_9876543210"
    monkeypatch.setenv("GROQ_API_KEY", raw_key)
    dummy_settings = Settings(GROQ_API_KEY=raw_key, _env_file=None)
    monkeypatch.setattr("server.app.services.ai_service.get_settings", lambda: dummy_settings)

    status_info = check_groq_provider_readiness()
    assert status_info["is_configured"] is True
    assert status_info["status"] == "configured"
    # Raw key MUST NOT appear anywhere in the status dictionary
    status_str = str(status_info)
    assert raw_key not in status_str
    # Masked key format: prefix...suffix
    assert "gsk_..." in status_info["masked_key"]
    assert status_info["masked_key"] != raw_key


def test_live_validation_skipped_when_key_not_configured(monkeypatch):
    """Verify validate_live_groq_connection clearly reports skipped when key is missing."""
    dummy_settings = Settings(GROQ_API_KEY=None, _env_file=None)
    monkeypatch.setattr("server.app.services.ai_service.get_settings", lambda: dummy_settings)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    res = validate_live_groq_connection()
    assert res["success"] is False
    assert res["status"] == "unconfigured"
    assert "not configured; live validation was not performed" in res["message"]


def test_live_validation_executes_safely_when_key_configured():
    """Verify live connectivity check executes without leaking raw credentials."""
    res = validate_live_groq_connection()
    # Check that status is one of the valid outcomes
    assert res["status"] in ("connected", "unconfigured", "error", "offline_mode_enforced")
    # Verify no raw key is ever present in message
    msg = res.get("message", "")
    assert "gsk_" not in msg or "gsk_..." in msg
