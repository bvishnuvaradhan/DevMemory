"""Comprehensive tests for LLM sanitized payload audits and frontend security evidence.

Validates:
1. Sanitized payload capture immediately before provider dispatch.
2. Adapter input payload matches persisted sanitized payload exactly.
3. Deterministic SHA-256 payload hash verification.
4. Transmission lifecycle states: prepared -> dispatched -> completed / failed / blocked_by_policy.
5. Strict secret redaction: zero persistence of raw secrets, keys, or auth headers in MongoDB.
6. Fail-closed policy enforcement: blocked on unredacted secrets, zero network dispatch, clean DB audit.
7. Graceful fallback integration in diagnose_error on policy violations.
8. Correlation across retries with attempt sequence numbering without overwriting earlier audits.
9. Strict multi-tenant project isolation.
10. Read-only API pagination, filtering, summary statistics, and single-item retrieval.
11. End-to-end integration linking created diagnoses to audit records.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import AsyncGenerator, Dict, Any, List, Optional
import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))

from ai_engine.diagnosis import diagnose_error
from ai_engine.llm_client import LLMClient
from ai_engine.retrieval import AuthorizationContext, IncidentRepository
from ai_engine.schemas import DiagnosisRequest
from app.config import get_settings
from app.db.indexes import init_indexes
from app.db.mongo import get_database
from app.main import app
from app.schemas.llm_audit import LLMRequestAuditItem
from app.services.ai_service import generate_and_store_incident_diagnosis
from app.services.llm_audit_service import (
    AuditedLLMClient,
    PayloadSecurityPolicyViolation,
    compute_payload_hash,
    get_audited_llm_client,
    get_audit_by_id,
    list_audits_for_project,
    get_project_security_summary,
)

TEST_DB_NAME = "devmemory_llm_audit_test"


class RecordingMockLLMClient:
    """Mock LLM client recording payloads passed to generate_diagnosis."""

    def __init__(self, should_fail: bool = False, fail_message: str = "Provider failure") -> None:
        self.should_fail = should_fail
        self.fail_message = fail_message
        self.call_count = 0
        self.last_system_prompt: Optional[str] = None
        self.last_user_prompt: Optional[str] = None
        self.provider_name = "mock"
        self.model = "mock-diagnostic-v1"

    def generate_diagnosis(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        if self.should_fail:
            raise RuntimeError(self.fail_message)
        return json.dumps({
            "event_id": "test_event",
            "summary": "Mock diagnosis completed successfully",
            "likely_cause": "Test failure cause",
            "hypotheses": ["Hypothesis A"],
            "recommended_steps": ["Step 1"],
            "evidence": ["Evidence 1"],
            "fix_status": "unverified",
        })


class InMemoryIncidentRepo(IncidentRepository):
    def get_project_incidents(self, project_id: str) -> List[Dict[str, Any]]:
        return []

    def get_cross_project_incidents(self, requesting_project_id: str) -> List[Dict[str, Any]]:
        return []


@pytest.fixture(scope="session")
def mongo_client():
    """Live MongoDB client session fixture for LLM audit tests."""
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
    client.drop_database(TEST_DB_NAME)
    client.close()


@pytest.fixture(autouse=True)
def test_db(mongo_client):
    """Clean MongoDB collections between LLM audit test runs."""
    db = mongo_client[TEST_DB_NAME]
    for col in [
        "projects",
        "command_runs",
        "incidents",
        "diagnoses",
        "fix_outcomes",
        "llm_request_audits",
    ]:
        db[col].delete_many({})

    init_indexes(db)
    app.dependency_overrides[get_database] = lambda: db
    yield db
    app.dependency_overrides.pop(get_database, None)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async test HTTP client bound to FastAPI application."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        yield client


# ==============================================================================
# Unit & Lifecycle Tests
# ==============================================================================

def test_audited_llm_client_captures_sanitized_payload_and_hash(test_db):
    """Test 1: Sanitized payload capture, provider input equality, and SHA-256 hash."""
    rec_client = RecordingMockLLMClient()
    client = AuditedLLMClient(
        db=test_db,
        project_id="proj_alpha",
        incident_id="inc_001",
        event_id="evt_001",
        underlying_client=rec_client,
    )

    sys_input = "You are a debugger. Diagnostic rules apply."
    user_input = "Incident: error in run. Log has token [REDACTED_API_KEY] and path /home/user/app.py."

    result = client.generate_diagnosis(sys_input, user_input)
    assert result is not None
    assert rec_client.call_count == 1

    # Assert underlying adapter input matches what client received
    assert rec_client.last_system_prompt == sys_input
    assert rec_client.last_user_prompt == user_input

    # Verify persisted record in MongoDB
    audit_doc = test_db.llm_request_audits.find_one({"project_id": "proj_alpha"})
    assert audit_doc is not None
    assert audit_doc["capture_boundary"] == "provider_adapter_input"
    assert audit_doc["transmission_status"] == "completed"

    payload = audit_doc["sanitized_payload"]
    assert payload["system_prompt"] == sys_input
    assert payload["user_prompt"] == user_input
    assert len(payload["messages"]) == 2

    # Deterministic SHA-256 verification
    expected_hash = compute_payload_hash(payload)
    assert audit_doc["payload_hash"] == expected_hash


def test_transmission_lifecycle_transitions_and_timing(test_db):
    """Test 2: Lifecycle transitions: prepared -> dispatched -> completed with timestamps."""
    rec_client = RecordingMockLLMClient()
    client = AuditedLLMClient(
        db=test_db,
        project_id="proj_alpha",
        incident_id="inc_lifecycle",
        event_id="evt_lifecycle",
        underlying_client=rec_client,
    )

    client.generate_diagnosis("System prompt", "User prompt")

    audit = test_db.llm_request_audits.find_one({"incident_id": "inc_lifecycle"})
    assert audit["transmission_status"] == "completed"
    assert audit["created_at"] is not None
    assert audit["dispatched_at"] is not None
    assert audit["completed_at"] is not None
    assert audit["duration_ms"] is not None
    assert audit["duration_ms"] >= 0.0
    assert audit["error_message"] is None


def test_transmission_lifecycle_failed_on_provider_exception(test_db):
    """Test 3: Provider exception transitions status to failed and sanitizes error message."""
    secret_in_error = "gsk_live_fail_secret_12345678901234567890"
    failing_client = RecordingMockLLMClient(should_fail=True, fail_message=f"401 Unauthorized: {secret_in_error}")
    client = AuditedLLMClient(
        db=test_db,
        project_id="proj_alpha",
        incident_id="inc_failure",
        underlying_client=failing_client,
    )

    with pytest.raises(RuntimeError):
        client.generate_diagnosis("System prompt", "User prompt")

    audit = test_db.llm_request_audits.find_one({"incident_id": "inc_failure"})
    assert audit is not None
    assert audit["transmission_status"] == "failed"
    assert audit["completed_at"] is not None
    assert audit["duration_ms"] is not None
    assert audit["error_message"] is not None
    # Verify error does not expose raw secret in plain text
    assert secret_in_error not in audit["error_message"]


def test_fail_closed_on_unredacted_credentials_no_dispatch_no_leak(test_db):
    """Test 4: Fail closed: unredacted credential blocks outbound transmission, no dispatch, raw secret never enters DB."""
    rec_client = RecordingMockLLMClient()
    client = AuditedLLMClient(
        db=test_db,
        project_id="proj_security",
        incident_id="inc_secret_test",
        underlying_client=rec_client,
    )

    # Use a dummy credential pattern that triggers outbound safety verification
    dummy_secret = "gsk_live_dummy_secret_abcdef1234567890123456"
    raw_prompt = f"Executing test with credential={dummy_secret}"

    with pytest.raises(PayloadSecurityPolicyViolation) as exc_info:
        client.generate_diagnosis("System instructions", raw_prompt)

    assert "Security verification blocked outbound transmission" in str(exc_info.value)
    # Crucial security guarantee: Provider client was NEVER called!
    assert rec_client.call_count == 0

    # Audit record in DB must be blocked_by_policy
    audit = test_db.llm_request_audits.find_one({"incident_id": "inc_secret_test"})
    assert audit is not None
    assert audit["transmission_status"] == "blocked_by_policy"
    assert audit["duration_ms"] == 0.0

    # Crucial security guarantee: raw secret NEVER entered DB document!
    audit_json = json.dumps(audit, default=str)
    assert dummy_secret not in audit_json


def test_fail_closed_integrates_with_diagnose_error_fallback(test_db):
    """Test 5: diagnose_error orchestrator catches policy violation and gracefully synthesizes fallback."""
    from unittest.mock import patch

    rec_client = RecordingMockLLMClient()
    audited_client = AuditedLLMClient(
        db=test_db,
        project_id="proj_orch",
        incident_id="inc_orch_fail",
        underlying_client=rec_client,
    )

    dummy_secret = "gsk_live_dummy_secret_12345678901234567890"
    req = DiagnosisRequest(
        event_id="evt_orch",
        command="python run.py --check-all",
        exit_code=1,
        error_message="Connection aborted",
        project_id="proj_orch",
    )
    auth = AuthorizationContext(project_id="proj_orch", user_id="test_user")
    repo = InMemoryIncidentRepo()

    # Simulate AuditedLLMClient failing closed on policy block during prompt generation
    with patch.object(
        audited_client,
        "generate_diagnosis",
        side_effect=PayloadSecurityPolicyViolation(
            "Security verification blocked outbound transmission: Unredacted sensitive credential pattern detected: api_key"
        ),
    ):
        resp = diagnose_error(
            request=req,
            auth_context=auth,
            repository=repo,
            llm_client=audited_client,
        )
        assert resp is not None
        assert resp.event_id == "evt_orch"
        assert "Failure during execution" in resp.summary or "Identified probable cause" in resp.summary
        assert rec_client.call_count == 0


def test_retry_correlation_and_attempt_increment(test_db):
    """Test 6: Multiple retry attempts for same incident increment attempt counter without overwriting."""
    rec_client = RecordingMockLLMClient()
    client = AuditedLLMClient(
        db=test_db,
        project_id="proj_retry",
        incident_id="inc_retry_001",
        underlying_client=rec_client,
    )

    # First attempt
    client.generate_diagnosis("Sys prompt 1", "User prompt 1")

    # Second attempt (e.g. recheck)
    client.generate_diagnosis("Sys prompt 2", "User prompt 2")

    audits = list(test_db.llm_request_audits.find({"incident_id": "inc_retry_001"}).sort("attempt", 1))
    assert len(audits) == 2
    assert audits[0]["attempt"] == 1
    assert audits[1]["attempt"] == 2
    assert audits[0]["audit_id"] != audits[1]["audit_id"]
    assert audits[0]["sanitized_payload"]["system_prompt"] == "Sys prompt 1"
    assert audits[1]["sanitized_payload"]["system_prompt"] == "Sys prompt 2"


def test_multi_tenant_project_isolation(test_db):
    """Test 7: Audits stored for Project Alpha cannot be viewed or fetched by Project Beta."""
    rec_client = RecordingMockLLMClient()

    client_a = AuditedLLMClient(db=test_db, project_id="proj_alpha", incident_id="inc_a", underlying_client=rec_client)
    client_b = AuditedLLMClient(db=test_db, project_id="proj_beta", incident_id="inc_b", underlying_client=rec_client)

    client_a.generate_diagnosis("System A", "User A")
    client_b.generate_diagnosis("System B", "User B")

    items_a, total_a = list_audits_for_project(test_db, project_id="proj_alpha")
    items_b, total_b = list_audits_for_project(test_db, project_id="proj_beta")

    assert total_a == 1
    assert total_b == 1
    assert items_a[0].project_id == "proj_alpha"
    assert items_b[0].project_id == "proj_beta"

    # Cross-project single item fetch must return None
    audit_a_id = items_a[0].audit_id
    assert get_audit_by_id(test_db, project_id="proj_beta", audit_id=audit_a_id) is None
    assert get_audit_by_id(test_db, project_id="proj_alpha", audit_id=audit_a_id) is not None


# ==============================================================================
# Read-Only API Endpoints Tests
# ==============================================================================

@pytest.mark.anyio
async def test_api_list_llm_audits_pagination_and_filtering(async_client: AsyncClient, test_db):
    """Test 8: API GET /api/v1/projects/{project_id}/llm-audits supports pagination and filtering."""
    now = datetime.now(timezone.utc)
    test_db.projects.insert_one({"project_id": "proj_api", "name": "API Test Project", "created_at": now, "updated_at": now})

    rec_client = RecordingMockLLMClient()
    client = AuditedLLMClient(db=test_db, project_id="proj_api", incident_id="inc_api_1", underlying_client=rec_client)

    # Create 3 audit records
    for i in range(3):
        client.generate_diagnosis(f"Sys {i}", f"User {i} [REDACTED_API_KEY]")

    # Pagination: limit 2, skip 0
    resp = await async_client.get("/api/v1/projects/proj_api/llm-audits?limit=2&skip=0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 3
    assert len(data["data"]["items"]) == 2
    assert data["data"]["limit"] == 2
    assert data["data"]["skip"] == 0

    # Skip 2
    resp_skip = await async_client.get("/api/v1/projects/proj_api/llm-audits?limit=2&skip=2")
    assert resp_skip.status_code == 200
    assert len(resp_skip.json()["data"]["items"]) == 1

    # Filter by provider
    resp_prov = await async_client.get("/api/v1/projects/proj_api/llm-audits?provider=mock")
    assert resp_prov.status_code == 200
    assert resp_prov.json()["data"]["total"] == 3

    # Filter by status
    resp_stat = await async_client.get("/api/v1/projects/proj_api/llm-audits?transmission_status=completed")
    assert resp_stat.status_code == 200
    assert resp_stat.json()["data"]["total"] == 3


@pytest.mark.anyio
async def test_api_get_security_summary(async_client: AsyncClient, test_db):
    """Test 9: API GET /api/v1/projects/{project_id}/llm-audits/summary computes live aggregated metrics."""
    now = datetime.now(timezone.utc)
    test_db.projects.insert_one({"project_id": "proj_sum", "name": "Summary Project", "created_at": now, "updated_at": now})

    rec_client = RecordingMockLLMClient()
    client = AuditedLLMClient(db=test_db, project_id="proj_sum", incident_id="inc_sum", underlying_client=rec_client)

    client.generate_diagnosis("Sys prompt", "User prompt with [REDACTED_API_KEY] and [REDACTED_PASSWORD]")

    resp = await async_client.get("/api/v1/projects/proj_sum/llm-audits/summary")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["project_id"] == "proj_sum"
    assert data["total_requests"] == 1
    assert data["status_counts"]["completed"] == 1
    assert data["total_redactions_applied"] >= 2
    assert "api_keys" in data["redaction_categories"]
    assert "passwords" in data["redaction_categories"]
    assert "mock" in data["providers_used"]


@pytest.mark.anyio
async def test_api_single_audit_and_project_isolation(async_client: AsyncClient, test_db):
    """Test 10: Single item lookup returns full details; cross-tenant query returns 404."""
    now = datetime.now(timezone.utc)
    test_db.projects.insert_one({"project_id": "proj_owner", "name": "Owner Project", "created_at": now, "updated_at": now})
    test_db.projects.insert_one({"project_id": "proj_other", "name": "Other Project", "created_at": now, "updated_at": now})

    rec_client = RecordingMockLLMClient()
    client = AuditedLLMClient(db=test_db, project_id="proj_owner", incident_id="inc_single", underlying_client=rec_client)
    client.generate_diagnosis("Sys", "User")

    audit = test_db.llm_request_audits.find_one({"project_id": "proj_owner"})
    audit_id = audit["audit_id"]

    # Owner access: 200 OK
    resp_owner = await async_client.get(f"/api/v1/projects/proj_owner/llm-audits/{audit_id}")
    assert resp_owner.status_code == 200
    assert resp_owner.json()["data"]["audit_id"] == audit_id

    # Non-owner access: 404 Not Found
    resp_other = await async_client.get(f"/api/v1/projects/proj_other/llm-audits/{audit_id}")
    assert resp_other.status_code == 404


@pytest.mark.anyio
async def test_end_to_end_generate_and_store_incident_diagnosis_creates_linked_audit(test_db):
    """Test 11: End-to-end generate_and_store_incident_diagnosis persists diagnosis and links diagnosis_id to audit."""
    now = datetime.now(timezone.utc)
    test_db.projects.insert_one({"project_id": "proj_e2e", "name": "E2E Project", "created_at": now, "updated_at": now})

    test_db.incidents.insert_one({
        "incident_id": "inc_e2e_001",
        "project_id": "proj_e2e",
        "event_id": "evt_e2e_001",
        "error_type": "RuntimeError",
        "error_message": "Null pointer exception [REDACTED_API_KEY]",
        "error_signature": "RuntimeError:Null pointer exception",
        "created_at": now,
        "is_public": False,
    })

    test_db.command_runs.insert_one({
        "event_id": "evt_e2e_001",
        "project_id": "proj_e2e",
        "command": "python test.py",
        "exit_code": 1,
        "duration_ms": 100,
        "created_at": now,
        "stderr": "Traceback (most recent call last)...",
    })

    mock_client = RecordingMockLLMClient()
    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=test_db,
        incident_id="inc_e2e_001",
        llm_client=mock_client,
    )
    assert diag_resp is not None
    assert is_new is True

    # Assert that an LLM audit record was automatically created
    audit = test_db.llm_request_audits.find_one({"incident_id": "inc_e2e_001"})
    assert audit is not None
    assert audit["project_id"] == "proj_e2e"
    assert audit["transmission_status"] == "completed"
    assert audit["diagnosis_id"] == diag_resp.diagnosis_id
    assert audit["capture_boundary"] == "provider_adapter_input"
