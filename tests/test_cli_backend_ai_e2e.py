"""End-to-End Integration Tests for CLI, Backend, and Member 3's AI Engine.

Validates:
1. End-to-end command failure ingestion -> incident creation -> AI diagnosis -> MongoDB persistence.
2. Offline deterministic fallback when external inference is disabled.
3. Multi-tenant project isolation and privacy (fail-closed cross-project boundaries).
4. Verified fix outcome lifecycle and its influence on subsequent retrieval reliability.
5. DevMemoryClient integration with diagnosis endpoint and Unverified Fix Guarantee.
"""

import os
import sys
from pathlib import Path
from typing import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import MongoClient

# Ensure app, devmemory, and ai_engine can be resolved
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.config import get_settings
from app.db.indexes import init_indexes
from app.db.mongo import get_database
from app.main import app
from devmemory.integration.client import DevMemoryClient
from devmemory.integration.models import IncidentPayload

TEST_DB_NAME = "devmemory_e2e_test"


@pytest.fixture(scope="session")
def e2e_mongo_client():
    """Live MongoDB client session fixture for e2e tests."""
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
def e2e_db(e2e_mongo_client):
    """Clean MongoDB collections between e2e test runs."""
    db = e2e_mongo_client[TEST_DB_NAME]
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
    app.dependency_overrides[get_database] = lambda: db
    yield db
    app.dependency_overrides.pop(get_database, None)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def e2e_async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async test HTTP client bound to FastAPI application."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.anyio
async def test_e2e_command_failure_to_ai_diagnosis(e2e_async_client: AsyncClient, e2e_db):
    """Validate full flow: register project -> submit failed run -> trigger diagnosis -> verify persistence."""
    # 1. Register project
    proj_resp = await e2e_async_client.post(
        "/api/v1/projects",
        json={"project_id": "proj-e2e-1", "name": "E2E Test Project", "language": "python"},
    )
    assert proj_resp.status_code == 201

    # 2. Ingest failed command run
    run_payload = {
        "event_id": "evt-e2e-fail-001",
        "project_id": "proj-e2e-1",
        "command": "python -m pytest tests/test_orders.py",
        "exit_code": 1,
        "duration_ms": 350,
        "stdout": "Running tests...\nFAILED",
        "stderr": "sqlite3.OperationalError: no such column: orders.discount_code\n  File 'app/models/order.py', line 42",
        "error_context": {
            "error_type": "OperationalError",
            "message": "sqlite3.OperationalError: no such column: orders.discount_code",
            "file_path": "app/models/order.py",
            "line": 42,
            "snippet": "def get_total(self):\n    return self.subtotal - self.discount_code.amount",
        },
    }
    run_resp = await e2e_async_client.post("/api/v1/runs", json=run_payload)
    assert run_resp.status_code == 201
    run_data = run_resp.json()["data"]
    incident_id = run_data["incident_id"]
    assert incident_id is not None
    assert incident_id.startswith("inc_")

    # Verify incident created in MongoDB
    inc_doc = e2e_db.incidents.find_one({"incident_id": incident_id})
    assert inc_doc is not None
    assert inc_doc["diagnosis_status"] == "pending"

    # 3. Trigger AI diagnosis via POST /api/v1/incidents/{incident_id}/diagnose
    diag_resp = await e2e_async_client.post(
        f"/api/v1/incidents/{incident_id}/diagnose?disable_external_inference=true"
    )
    assert diag_resp.status_code in (200, 201)
    diag_data = diag_resp.json()["data"]

    # 4. Verify diagnosis structure
    assert diag_data["incident_id"] == incident_id
    assert diag_data["project_id"] == "proj-e2e-1"
    assert len(diag_data["summary"]) > 0
    assert len(diag_data["hypotheses"]) > 0
    assert diag_data["suggested_fix"] is not None
    assert len(diag_data["evidence"]) > 0

    # 5. Verify database persistence and updated incident status
    persisted_diag = e2e_db.diagnoses.find_one({"incident_id": incident_id})
    assert persisted_diag is not None
    assert persisted_diag["summary"] == diag_data["summary"]

    updated_inc = e2e_db.incidents.find_one({"incident_id": incident_id})
    assert updated_inc["diagnosis_status"] == "diagnosed"

    # 6. Verify subsequent GET /api/v1/incidents/{incident_id}/diagnosis returns stored diagnosis
    get_diag_resp = await e2e_async_client.get(f"/api/v1/incidents/{incident_id}/diagnosis")
    assert get_diag_resp.status_code == 200
    assert get_diag_resp.json()["data"]["summary"] == diag_data["summary"]


@pytest.mark.anyio
async def test_e2e_multi_tenant_project_isolation(e2e_async_client: AsyncClient, e2e_db):
    """Validate that private incidents from Project A are strictly excluded when diagnosing Project B."""
    # 1. Register two distinct projects
    await e2e_async_client.post("/api/v1/projects", json={"project_id": "proj-alpha", "name": "Project Alpha"})
    await e2e_async_client.post("/api/v1/projects", json={"project_id": "proj-beta", "name": "Project Beta"})

    # 2. Ingest private incident in Project Alpha
    await e2e_async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt-alpha-001",
            "project_id": "proj-alpha",
            "command": "python app.py",
            "exit_code": 1,
            "duration_ms": 100,
            "stderr": "ValueError: confidential payment token missing",
            "error_context": {
                "error_type": "ValueError",
                "message": "ValueError: confidential payment token missing",
            },
        },
    )
    # Ensure incident in Alpha is private (is_public=False)
    e2e_db.incidents.update_one({"project_id": "proj-alpha"}, {"$set": {"is_public": False}})

    # 3. Ingest similar error in Project Beta
    beta_run_resp = await e2e_async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt-beta-001",
            "project_id": "proj-beta",
            "command": "python worker.py",
            "exit_code": 1,
            "duration_ms": 120,
            "stderr": "ValueError: confidential payment token missing",
            "error_context": {
                "error_type": "ValueError",
                "message": "ValueError: confidential payment token missing",
            },
        },
    )
    beta_inc_id = beta_run_resp.json()["data"]["incident_id"]

    # 4. Diagnose Beta without cross-project authorization
    diag_resp_1 = await e2e_async_client.post(
        f"/api/v1/incidents/{beta_inc_id}/diagnose?allow_cross_project=true&has_cross_project_read=false&disable_external_inference=true"
    )
    assert diag_resp_1.status_code in (200, 201)
    matched_memory_1 = diag_resp_1.json()["data"].get("matched_memory", [])
    matched_ids_1 = [m["source_id"] for m in matched_memory_1]
    # Private Alpha incident MUST NOT be present
    assert "inc_evt-alpha-001" not in matched_ids_1

    # 5. Mark Alpha incident as public, but keep server authorization disabled
    e2e_db.incidents.update_one({"project_id": "proj-alpha"}, {"$set": {"is_public": True}})
    # Clear cached diagnosis
    e2e_db.diagnoses.delete_many({"incident_id": beta_inc_id})

    diag_resp_2 = await e2e_async_client.post(
        f"/api/v1/incidents/{beta_inc_id}/diagnose?allow_cross_project=true&has_cross_project_read=false&disable_external_inference=true"
    )
    matched_ids_2 = [m["source_id"] for m in diag_resp_2.json()["data"].get("matched_memory", [])]
    # Still excluded because has_cross_project_read is False (fail-closed!)
    assert "inc_evt-alpha-001" not in matched_ids_2

    # 6. Now grant server authorization: has_cross_project_read=true
    e2e_db.diagnoses.delete_many({"incident_id": beta_inc_id})
    diag_resp_3 = await e2e_async_client.post(
        f"/api/v1/incidents/{beta_inc_id}/diagnose?allow_cross_project=true&has_cross_project_read=true&disable_external_inference=true"
    )
    matched_ids_3 = [m["source_id"] for m in diag_resp_3.json()["data"].get("matched_memory", [])]
    # Now public Alpha incident IS matched cross-project!
    assert "inc_evt-alpha-001" in matched_ids_3


@pytest.mark.anyio
async def test_e2e_verified_fix_enhances_memory_retrieval(e2e_async_client: AsyncClient, e2e_db):
    """Validate that when an incident fix is verified with execution evidence, subsequent diagnosis recognizes it."""
    # 1. Register project
    await e2e_async_client.post("/api/v1/projects", json={"project_id": "proj-fix-test", "name": "Fix Verification Project"})

    # 2. Ingest first incident
    run1 = await e2e_async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt-fix-001",
            "project_id": "proj-fix-test",
            "command": "python service.py",
            "exit_code": 1,
            "duration_ms": 100,
            "stderr": "KeyError: 'database_host'",
            "error_context": {
                "error_type": "KeyError",
                "message": "KeyError: 'database_host'",
                "snippet": "host = config['database_host']",
            },
        },
    )
    inc1_id = run1.json()["data"]["incident_id"]

    # 3. Register proposed fix for Incident 1
    fix_resp = await e2e_async_client.post(
        f"/api/v1/incidents/{inc1_id}/fixes",
        json={"description": "Use config.get('database_host', 'localhost') fallback"},
    )
    assert fix_resp.status_code == 201
    fix_id = fix_resp.json()["data"]["fix_id"]

    # 4. Mark fix verified with valid command evidence
    verify_resp = await e2e_async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={
            "status": "applied",
        },
    )
    assert verify_resp.status_code == 200

    verify_resp_2 = await e2e_async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={
            "status": "verifying",
            "verification_command": "python -m pytest tests/test_config.py",
            "verification_exit_code": 0,
            "verification_method": "automated_test",
        },
    )
    assert verify_resp_2.status_code == 200

    verify_resp_3 = await e2e_async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={
            "status": "verified",
        },
    )
    assert verify_resp_3.status_code == 200
    assert verify_resp_3.json()["data"]["status"] == "verified"

    # 5. Ingest second incident with same error signature in same project
    run2 = await e2e_async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt-fix-002",
            "project_id": "proj-fix-test",
            "command": "python service.py",
            "exit_code": 1,
            "duration_ms": 110,
            "stderr": "KeyError: 'database_host'",
            "error_context": {
                "error_type": "KeyError",
                "message": "KeyError: 'database_host'",
            },
        },
    )
    inc2_id = run2.json()["data"]["incident_id"]

    # 6. Diagnose Incident 2
    diag2_resp = await e2e_async_client.post(
        f"/api/v1/incidents/{inc2_id}/diagnose?disable_external_inference=true"
    )
    assert diag2_resp.status_code in (200, 201)
    diag2_data = diag2_resp.json()["data"]

    # 7. Verify Incident 1 is matched in memory
    matched = diag2_data.get("matched_memory", [])
    matched_ids = [m["source_id"] for m in matched]
    assert inc1_id in matched_ids


def test_e2e_devmemory_client_diagnose_integration(monkeypatch):
    """Validate DevMemoryClient's diagnose_incident method against mocked endpoint."""
    import json
    import urllib.request
    from unittest.mock import MagicMock

    client = DevMemoryClient(base_url="http://localhost:8000")

    mock_resp_data = {
        "success": True,
        "data": {
            "diagnosis_id": "diag_test_123",
            "incident_id": "inc_e2e_456",
            "project_id": "proj_client_test",
            "summary": "Missing environment variable DATABASE_URL",
            "hypotheses": [
                {"cause": ".env file was not loaded", "is_observed": False, "details": None}
            ],
            "suggested_fix": "Add DATABASE_URL to your .env configuration",
            "matched_memory": [
                {"source_id": "inc_past_001", "source_type": "project_memory", "relevance_reason": "Exact signature match"}
            ],
            "evidence": ["KeyError: 'DATABASE_URL'"],
            "confidence": 0.95,
            "source": "ai_engine/groq-llama-3.3-70b",
        },
        "error": None,
    }

    mock_http_resp = MagicMock()
    mock_http_resp.getcode.return_value = 200
    mock_http_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_http_resp.__enter__.return_value = mock_http_resp

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: mock_http_resp)

    res = client.diagnose_incident(incident_id="inc_e2e_456", event_id="evt_789")
    assert res is not None
    assert res.status == "success"
    assert res.incident_id == "inc_e2e_456"
    assert res.event_id == "evt_789"
    assert res.probable_cause == "Missing environment variable DATABASE_URL"
    assert len(res.hypotheses) == 1
    assert "Add DATABASE_URL" in res.suggested_steps[0]
    assert len(res.similar_incidents) == 1
    assert res.similar_incidents[0].incident_id == "inc_past_001"
    # Unverified Fix Guarantee strictly preserved:
    assert res.is_verified_fix is False


@pytest.mark.anyio
async def test_e2e_secret_redaction_in_diagnosis_pipeline(e2e_async_client: AsyncClient, e2e_db):
    """Validate that raw secrets in commands or tracebacks are redacted in AI diagnosis output."""
    await e2e_async_client.post("/api/v1/projects", json={"project_id": "proj-secrets", "name": "Secrets Project"})

    raw_secret_key = "sk-live_SECRET1234567890abcdef1234567890"
    raw_db_uri = "mongodb://admin:super_secret_password_999@cluster0.mongodb.net/prod"

    run_resp = await e2e_async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt-secret-001",
            "project_id": "proj-secrets",
            "command": f"python run.py --key {raw_secret_key}",
            "exit_code": 1,
            "duration_ms": 150,
            "stderr": f"ConnectionError: Failed to connect to {raw_db_uri}",
            "error_context": {
                "error_type": "ConnectionError",
                "message": f"ConnectionError: Failed to connect to {raw_db_uri} with token {raw_secret_key}",
            },
        },
    )
    inc_id = run_resp.json()["data"]["incident_id"]

    diag_resp = await e2e_async_client.post(
        f"/api/v1/incidents/{inc_id}/diagnose?disable_external_inference=true"
    )
    assert diag_resp.status_code in (200, 201)
    diag_data = diag_resp.json()["data"]

    # Raw secrets must NOT appear anywhere in diagnosis
    diag_str = str(diag_data)
    assert raw_secret_key not in diag_str
    assert "super_secret_password_999" not in diag_str


@pytest.mark.anyio
async def test_e2e_diagnose_nonexistent_incident_returns_404(e2e_async_client: AsyncClient):
    """Validate that attempting to diagnose a non-existent incident returns 404."""
    resp = await e2e_async_client.post("/api/v1/incidents/inc_nonexistent_999/diagnose")
    assert resp.status_code == 404
