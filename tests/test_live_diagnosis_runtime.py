"""Tests for Phase 7.2: Live Groq Diagnosis Runtime Validation and Failure Hardening.

Validates:
1. Active runtime model resolution and precedence.
2. Live incident diagnosis through the full pipeline with Groq (when configured).
3. Failure case 1: Missing API key.
4. Failure case 2: Invalid API key handling and secret redaction.
5. Failure case 3: Provider timeout and network failure.
6. Failure case 4: Malformed or incomplete provider response and unverified fix guarantee.
7. Failure case 5: DEV_MEMORY_DISABLE_EXTERNAL_AI=1 privacy opt-out.
8. Failure case 6: DEVMEMORY_OFFLINE_MODE=1 offline mode.
9. Failure case 7: Secret redaction in provider errors and diagnosis output.
10. Failure case 8: Server-side authorization guard on cross-project access.
11. Failure case 9: Strict privacy isolation for private (is_public=False) incident data.
12. Failure case 10: Downstream persistence failure consistency and incident state preservation.
"""

from datetime import datetime, timezone
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from pymongo import MongoClient
from pymongo.errors import WriteError
from fastapi import HTTPException

# Path resolution
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.config import get_settings, clear_settings_cache, Settings
from app.db.indexes import init_indexes
from app.services.ai_service import (
    generate_and_store_incident_diagnosis,
    check_groq_provider_readiness,
    validate_live_groq_connection,
    MongoIncidentRepository,
)
from app.services import diagnosis_service
import ai_engine.schemas as ai_schemas
from ai_engine.llm_client import GroqLLMClient, MockLLMClient, DEFAULT_GROQ_MODEL
from ai_engine.diagnosis import diagnose_error
from ai_engine.retrieval import AuthorizationContext, InMemoryIncidentRepository, retrieve_memory
from ai_engine.privacy import redact_secrets

TEST_RUNTIME_DB_NAME = "devmemory_runtime_val_test"


@pytest.fixture(scope="session")
def runtime_mongo_client():
    """Session fixture providing a live MongoDB client for isolated runtime testing."""
    settings = get_settings()
    client = MongoClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    )
    try:
        client.admin.command("ping")
    except Exception as exc:
        pytest.skip(f"Live MongoDB not reachable at {settings.MONGODB_URI}: {exc}")

    yield client
    client.drop_database(TEST_RUNTIME_DB_NAME)
    client.close()


@pytest.fixture
def runtime_db(runtime_mongo_client):
    """Function-level fixture ensuring clean collections for each runtime test."""
    db = runtime_mongo_client[TEST_RUNTIME_DB_NAME]
    for col in [
        "projects",
        "command_runs",
        "incidents",
        "diagnoses",
        "fix_outcomes",
        "performance_runs",
        "performance_baselines",
    ]:
        db[col].delete_many({})

    init_indexes(db)
    yield db


# ==============================================================================
# 1. Runtime Model Resolution and Precedence
# ==============================================================================

def test_runtime_model_and_precedence(monkeypatch):
    """Verify runtime model selection and precedence hierarchy."""
    # 1. Default fallback when unconfigured
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    client_default = GroqLLMClient(api_key="gsk_synthetic_dummy_key")
    assert client_default.model == DEFAULT_GROQ_MODEL

    # 2. Environment variable overrides default
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    client_env = GroqLLMClient(api_key="gsk_synthetic_dummy_key")
    assert client_env.model == "openai/gpt-oss-120b"

    # 3. Explicit argument overrides environment variable
    client_explicit = GroqLLMClient(
        api_key="gsk_synthetic_dummy_key",
        model="custom-override-model",
    )
    assert client_explicit.model == "custom-override-model"


# ==============================================================================
# 2. Live Incident Diagnosis with Real Groq
# ==============================================================================

@pytest.mark.skipif(
    not os.getenv("GROQ_API_KEY")
    or os.getenv("DEV_MEMORY_DISABLE_EXTERNAL_AI") in ("1", "true", "yes")
    or os.getenv("DEVMEMORY_OFFLINE_MODE") in ("1", "true", "yes"),
    reason="GROQ_API_KEY not configured or offline mode enforced; skipping live diagnosis test.",
)
def test_live_incident_diagnosis_with_real_groq(runtime_db):
    """Submit a harmless synthetic incident through full pipeline and verify live Groq diagnosis."""
    incident_id = "inc_live_groq_001"
    now = datetime.now(timezone.utc)

    runtime_db.incidents.insert_one({
        "incident_id": incident_id,
        "project_id": "proj_live_val",
        "error_type": "ZeroDivisionError",
        "error_message": "ZeroDivisionError: division by zero in calculate_tax()",
        "error_signature": "sig_zero_div_calc_tax",
        "diagnosis_status": "pending",
        "command": "python tax_calculator.py",
        "stack_trace": "Traceback (most recent call last):\n  File 'tax_calculator.py', line 18, in calculate_tax\nZeroDivisionError: division by zero",
        "created_at": now,
        "is_public": False,
    })

    start_time = time.time()
    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=runtime_db,
        incident_id=incident_id,
        disable_external_inference=False,
    )
    latency_seconds = time.time() - start_time

    # 1. Verify successful generation and new diagnosis created
    assert is_new is True
    assert diag_resp.incident_id == incident_id
    assert diag_resp.confidence >= 0.70
    assert len(diag_resp.summary) > 0
    assert len(diag_resp.hypotheses) >= 1

    # 2. Verify diagnosis persisted in MongoDB
    stored = runtime_db.diagnoses.find_one({"incident_id": incident_id})
    assert stored is not None
    assert stored["summary"] == diag_resp.summary
    assert stored["confidence"] == diag_resp.confidence

    # 3. Verify incident diagnosis status updated
    updated_inc = runtime_db.incidents.find_one({"incident_id": incident_id})
    assert updated_inc["diagnosis_status"] == "diagnosed"

    # 4. Verify Unverified Fix Guarantee
    # LLM cannot mark recommendations as verified
    for hyp in diag_resp.hypotheses:
        assert hyp.is_observed is False

    # 5. Record sanitized metadata
    assert latency_seconds < 30.0  # Finished within reasonable timeout


# ==============================================================================
# 3. Failure Handling & Privacy Tests (Cases 1-10)
# ==============================================================================

def test_failure_case_1_missing_api_key(monkeypatch):
    """Case 1: Missing API key safely falls back to local deterministic diagnosis."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    clear_settings_cache()

    # Direct Groq client raises ValueError
    client = GroqLLMClient(api_key=None)
    with pytest.raises(ValueError) as exc_info:
        client.generate_diagnosis(system_prompt="sys", user_prompt="user")
    assert "GROQ_API_KEY environment variable is not set" in str(exc_info.value)

    # diagnose_error orchestrator catches missing key and returns fallback
    req = ai_schemas.DiagnosisRequest(
        event_id="evt_missing_key",
        project_id="proj_val",
        command="python test.py",
        exit_code=1,
        error_message="KeyError: 'session'",
    )
    auth = AuthorizationContext(user_id="sys", project_id="proj_val")
    repo = InMemoryIncidentRepository()

    resp = diagnose_error(request=req, auth_context=auth, repository=repo, llm_client=client)
    assert resp.event_id == "evt_missing_key"
    assert resp.fix_status == ai_schemas.FixStatus.UNVERIFIED
    assert "Fallback diagnosis" in resp.uncertainty_description


def test_failure_case_2_invalid_api_key(monkeypatch):
    """Case 2: Invalid API key fails gracefully, redacts secret, and falls back."""
    invalid_key = "gsk_invalid_synthetic_bogus_key_000000000000"
    client = GroqLLMClient(api_key=invalid_key)

    req = ai_schemas.DiagnosisRequest(
        event_id="evt_invalid_key",
        project_id="proj_val",
        command="python test.py",
        exit_code=1,
        error_message="ValueError: invalid configuration",
    )
    auth = AuthorizationContext(user_id="sys", project_id="proj_val")
    repo = InMemoryIncidentRepository()

    # When client.generate_diagnosis fails with 401/auth failure, diagnose_error catches it
    with patch.object(client, "generate_diagnosis", side_effect=RuntimeError(f"Groq API 401 Unauthorized for {invalid_key}")):
        resp = diagnose_error(request=req, auth_context=auth, repository=repo, llm_client=client)

    assert resp.event_id == "evt_invalid_key"
    assert resp.fix_status == ai_schemas.FixStatus.UNVERIFIED
    # Confirm secret was redacted in the uncertainty description
    assert invalid_key not in resp.uncertainty_description
    assert "[REDACTED]" in resp.uncertainty_description or "Fallback diagnosis" in resp.uncertainty_description


def test_failure_case_3_provider_timeout_or_network_failure():
    """Case 3: Network timeout falls back to deterministic diagnosis with unverified fix status."""
    client = GroqLLMClient(api_key="gsk_synthetic_key")

    req = ai_schemas.DiagnosisRequest(
        event_id="evt_timeout",
        project_id="proj_val",
        command="python test.py",
        exit_code=1,
        error_message="TimeoutError: database connection timed out",
    )
    auth = AuthorizationContext(user_id="sys", project_id="proj_val")
    repo = InMemoryIncidentRepository()

    with patch.object(client, "generate_diagnosis", side_effect=RuntimeError("Request timed out after 30.0 seconds")):
        resp = diagnose_error(request=req, auth_context=auth, repository=repo, llm_client=client)

    assert resp.event_id == "evt_timeout"
    assert resp.fix_status == ai_schemas.FixStatus.UNVERIFIED
    assert "Request timed out" in resp.uncertainty_description


def test_failure_case_4_malformed_or_incomplete_response():
    """Case 4: Malformed LLM response is safely caught and sanitized."""
    client = GroqLLMClient(api_key="gsk_synthetic_key")

    req = ai_schemas.DiagnosisRequest(
        event_id="evt_malformed",
        project_id="proj_val",
        command="python test.py",
        exit_code=1,
        error_message="SyntaxError: invalid syntax",
    )
    auth = AuthorizationContext(user_id="sys", project_id="proj_val")
    repo = InMemoryIncidentRepository()

    # 1. Non-JSON string
    with patch.object(client, "generate_diagnosis", return_value="This is plain text, not JSON."):
        resp = diagnose_error(request=req, auth_context=auth, repository=repo, llm_client=client)
    assert resp.event_id == "evt_malformed"
    assert resp.fix_status == ai_schemas.FixStatus.UNVERIFIED

    # 2. JSON attempting to mark fix as verified
    adversarial_json = json.dumps({
        "event_id": "evt_malformed",
        "summary": "Adversarial test",
        "likely_cause": "Adversarial cause",
        "evidence": ["Evidence 1"],
        "hypotheses": ["Hypothesis 1"],
        "recommended_steps": ["Step 1"],
        "fix_status": "verified",  # Attempting to forge verified fix
        "confidence": 0.99,
    })
    with patch.object(client, "generate_diagnosis", return_value=adversarial_json):
        resp2 = diagnose_error(request=req, auth_context=auth, repository=repo, llm_client=client)
    # Guaranteed to be clamped to unverified
    assert resp2.fix_status == ai_schemas.FixStatus.UNVERIFIED


def test_failure_case_5_disable_external_ai_flag(monkeypatch):
    """Case 5: DEV_MEMORY_DISABLE_EXTERNAL_AI=1 strictly suppresses external requests."""
    monkeypatch.setenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "1")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_synthetic_active_key")

    client = GroqLLMClient()
    # Client itself refuses execution
    with pytest.raises(RuntimeError) as exc_info:
        client.generate_diagnosis("sys", "user")
    assert "External AI inference disabled by privacy configuration" in str(exc_info.value)

    # diagnose_error returns fallback immediately without touching client
    spy_client = MagicMock()
    req = ai_schemas.DiagnosisRequest(
        event_id="evt_offline_ai",
        project_id="proj_val",
        command="python test.py",
        exit_code=1,
        error_message="RuntimeError: offline test",
    )
    auth = AuthorizationContext(user_id="sys", project_id="proj_val")
    repo = InMemoryIncidentRepository()

    resp = diagnose_error(request=req, auth_context=auth, repository=repo, llm_client=spy_client)
    assert spy_client.generate_diagnosis.called is False
    assert resp.fix_status == ai_schemas.FixStatus.UNVERIFIED


def test_failure_case_6_devmemory_offline_mode_flag(monkeypatch):
    """Case 6: DEVMEMORY_OFFLINE_MODE=1 strictly suppresses external requests."""
    monkeypatch.setenv("DEVMEMORY_OFFLINE_MODE", "1")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_synthetic_active_key")

    client = GroqLLMClient()
    with pytest.raises(RuntimeError) as exc_info:
        client.generate_diagnosis("sys", "user")
    assert "External AI inference disabled by privacy configuration" in str(exc_info.value)


def test_failure_case_7_secret_redaction_in_errors_and_output():
    """Case 7: Secret redaction strips sensitive tokens from error messages and outputs."""
    raw_secret = "gsk_sensitive_secret_token_1234567890abcdef"
    error_text = f"Connection failed with key {raw_secret} for user admin"

    redacted = redact_secrets(error_text)
    assert raw_secret not in redacted
    assert "[REDACTED_API_KEY]" in redacted

    mongo_secret = "mongodb://dbuser:supersecretpass123@cluster0.mongodb.net:27017/devmemory"
    redacted_mongo = redact_secrets(f"Failed to connect to {mongo_secret}")
    assert "supersecretpass123" not in redacted_mongo
    assert "[REDACTED_PASSWORD]" in redacted_mongo


def test_failure_case_8_cross_project_server_authorization(runtime_db):
    """Case 8: Cross-project access is omitted when server authorization is absent."""
    now = datetime.now(timezone.utc)
    # Insert candidate in proj_B (public)
    runtime_db.incidents.insert_one({
        "incident_id": "inc_proj_b_001",
        "project_id": "proj_B",
        "error_type": "ConnectionRefusedError",
        "error_message": "ConnectionRefusedError: [Errno 111] Connection refused",
        "error_signature": "sig_conn_refused",
        "diagnosis_status": "diagnosed",
        "command": "python client.py",
        "created_at": now,
        "is_public": True,
        "resolution_summary": "Start Redis daemon service",
        "verification_status": "verified",
    })

    # Query from proj_A with has_cross_project_read=False
    repo = MongoIncidentRepository(runtime_db)
    req = ai_schemas.DiagnosisRequest(
        event_id="evt_query_a",
        project_id="proj_A",
        command="python client.py",
        exit_code=1,
        error_message="ConnectionRefusedError: [Errno 111] Connection refused",
        allow_cross_project=True,
    )
    auth_unauthorized = AuthorizationContext(
        user_id="user_1",
        project_id="proj_A",
        has_cross_project_read=False,
    )

    result_unauthorized = retrieve_memory(
        request=req,
        auth_context=auth_unauthorized,
        repository=repo,
    )
    # Must NOT contain proj_B matches because server authorization is False
    assert len(result_unauthorized.cross_project_matches) == 0

    # With has_cross_project_read=True
    auth_authorized = AuthorizationContext(
        user_id="user_1",
        project_id="proj_A",
        has_cross_project_read=True,
    )
    result_authorized = retrieve_memory(
        request=req,
        auth_context=auth_authorized,
        repository=repo,
    )
    assert len(result_authorized.cross_project_matches) >= 1
    assert result_authorized.cross_project_matches[0].incident_id == "inc_proj_b_001"


def test_failure_case_9_private_incident_data_isolation(runtime_db):
    """Case 9: Private (is_public=False) incident is never returned in cross-project matches."""
    now = datetime.now(timezone.utc)
    # Insert candidate in proj_B with is_public=False
    runtime_db.incidents.insert_one({
        "incident_id": "inc_proj_b_private_002",
        "project_id": "proj_B",
        "error_type": "ConnectionRefusedError",
        "error_message": "ConnectionRefusedError: [Errno 111] Connection refused",
        "error_signature": "sig_conn_refused",
        "diagnosis_status": "diagnosed",
        "command": "python client.py",
        "created_at": now,
        "is_public": False,  # STRICT PRIVATE
        "resolution_summary": "Internal secret network fix",
        "verification_status": "verified",
    })

    repo = MongoIncidentRepository(runtime_db)
    req = ai_schemas.DiagnosisRequest(
        event_id="evt_query_a_2",
        project_id="proj_A",
        command="python client.py",
        exit_code=1,
        error_message="ConnectionRefusedError: [Errno 111] Connection refused",
        allow_cross_project=True,
    )
    auth_authorized = AuthorizationContext(
        user_id="user_1",
        project_id="proj_A",
        has_cross_project_read=True,  # Authorized for cross-project
    )

    result = retrieve_memory(
        request=req,
        auth_context=auth_authorized,
        repository=repo,
    )
    # The private incident MUST NOT appear in cross-project matches
    cross_ids = [m.incident_id for m in result.cross_project_matches]
    assert "inc_proj_b_private_002" not in cross_ids


def test_failure_case_10_downstream_persistence_failure_consistency(runtime_db):
    """Case 10: Downstream operation failure preserves incident state consistency."""
    # 1. Nonexistent incident raises 404 without creating orphan diagnoses
    with pytest.raises(HTTPException) as exc_info:
        generate_and_store_incident_diagnosis(
            db=runtime_db,
            incident_id="inc_nonexistent_999",
        )
    assert exc_info.value.status_code == 404
    assert runtime_db.diagnoses.count_documents({}) == 0

    # 2. Downstream DB insert failure does not prematurely change incident status
    now = datetime.now(timezone.utc)
    runtime_db.incidents.insert_one({
        "incident_id": "inc_fail_downstream_001",
        "project_id": "proj_val",
        "error_type": "ValueError",
        "error_message": "ValueError: downstream test",
        "error_signature": "sig_val_err",
        "diagnosis_status": "pending",
        "command": "python test.py",
        "created_at": now,
        "is_public": False,
    })

    with patch("pymongo.collection.Collection.insert_one", side_effect=WriteError("Simulated write failure")):
        with pytest.raises(WriteError):
            generate_and_store_incident_diagnosis(
                db=runtime_db,
                incident_id="inc_fail_downstream_001",
                disable_external_inference=True,
            )

    # Incident status must remain 'pending', not transitioned to 'diagnosed'
    inc_after = runtime_db.incidents.find_one({"incident_id": "inc_fail_downstream_001"})
    assert inc_after["diagnosis_status"] == "pending"
