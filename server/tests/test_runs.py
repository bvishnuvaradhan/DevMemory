"""Tests for command-run ingestion, idempotency, conflict detection, and history."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def registered_project(test_db, async_client: AsyncClient):
    """Helper fixture providing an initialized project."""
    res = await async_client.post(
        "/api/v1/projects",
        json={"name": "ShopApp", "project_id": "proj_shopapp", "language": "javascript"},
    )
    assert res.status_code == 201
    return "proj_shopapp"


@pytest.mark.anyio
async def test_ingest_run_success(registered_project, async_client: AsyncClient):
    """Scenario 5: Successful command-run ingestion returns 201 and envelope."""
    payload = {
        "event_id": "evt_run_001",
        "project_id": registered_project,
        "command": "npm test",
        "exit_code": 0,
        "duration_ms": 1250,
        "stdout": "PASS src/App.test.jsx",
        "stderr": "",
        "environment": {"os": "Windows", "runtime_version": "v22.19.0"},
    }
    response = await async_client.post("/api/v1/runs", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["event_id"] == "evt_run_001"
    assert data["status"] == "success"
    assert data["idempotent"] is False
    assert data["incident_id"] is None


@pytest.mark.anyio
async def test_get_run_by_event_id(registered_project, async_client: AsyncClient):
    """Scenario 6: Run retrieval by event ID."""
    payload = {
        "event_id": "evt_run_lookup",
        "project_id": registered_project,
        "command": "python -m pytest",
        "exit_code": 0,
        "duration_ms": 500,
    }
    await async_client.post("/api/v1/runs", json=payload)

    response = await async_client.get("/api/v1/runs/evt_run_lookup")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["event_id"] == "evt_run_lookup"
    assert body["data"]["command"] == "python -m pytest"


@pytest.mark.anyio
async def test_duplicate_run_idempotency(registered_project, test_db, async_client: AsyncClient):
    """Scenario 7: Duplicate event submissions do not create duplicate runs (idempotent 200)."""
    payload = {
        "event_id": "evt_run_retry",
        "project_id": registered_project,
        "command": "pytest",
        "exit_code": 0,
        "duration_ms": 300,
    }

    # Initial submission
    res1 = await async_client.post("/api/v1/runs", json=payload)
    assert res1.status_code == 201
    assert res1.json()["data"]["idempotent"] is False

    # Retry submission
    res2 = await async_client.post("/api/v1/runs", json=payload)
    assert res2.status_code == 200
    assert res2.json()["data"]["idempotent"] is True

    # Database count remains strictly 1
    count = test_db.command_runs.count_documents({"event_id": "evt_run_retry"})
    assert count == 1


@pytest.mark.anyio
async def test_conflicting_event_id_payload(registered_project, async_client: AsyncClient):
    """Scenario 8: Same event ID with conflicting payload returns 409 Conflict."""
    payload1 = {
        "event_id": "evt_conflict_001",
        "project_id": registered_project,
        "command": "git status",
        "exit_code": 0,
        "duration_ms": 100,
    }
    res1 = await async_client.post("/api/v1/runs", json=payload1)
    assert res1.status_code == 201

    payload2 = {
        "event_id": "evt_conflict_001",
        "project_id": registered_project,
        "command": "cargo build",  # Different command under same event_id!
        "exit_code": 1,
        "duration_ms": 4000,
    }
    res2 = await async_client.post("/api/v1/runs", json=payload2)
    assert res2.status_code == 409
    body = res2.json()
    assert body["success"] is False
    assert "Conflict: event_id 'evt_conflict_001' already exists" in body["error"]


@pytest.mark.anyio
async def test_invalid_run_payload_validation(async_client: AsyncClient):
    """Scenario 9: Missing required fields returns HTTP 422."""
    payload = {"command": "echo test"}  # Missing event_id, project_id, exit_code, duration_ms
    response = await async_client.post("/api/v1/runs", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "Validation failed" in body["error"]


@pytest.mark.anyio
async def test_negative_duration_rejected(registered_project, async_client: AsyncClient):
    """Scenario 10: Negative execution duration is rejected with HTTP 422."""
    payload = {
        "event_id": "evt_neg_dur",
        "project_id": registered_project,
        "command": "npm test",
        "exit_code": 0,
        "duration_ms": -50,
    }
    response = await async_client.post("/api/v1/runs", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "duration_ms" in body["error"]


@pytest.mark.anyio
async def test_run_unknown_project_rejected(async_client: AsyncClient):
    """Scenario 11: Unknown project run ingestion returns HTTP 404."""
    payload = {
        "event_id": "evt_ghost_proj",
        "project_id": "proj_non_existent",
        "command": "pytest",
        "exit_code": 0,
        "duration_ms": 100,
    }
    response = await async_client.post("/api/v1/runs", json=payload)
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert "not found" in body["error"].lower()


@pytest.mark.anyio
async def test_failed_run_creates_incident(registered_project, test_db, async_client: AsyncClient):
    """Scenario 12: Failed run with error context automatically creates one incident."""
    payload = {
        "event_id": "evt_fail_001",
        "project_id": registered_project,
        "command": "npm test",
        "exit_code": 1,
        "duration_ms": 820,
        "stderr": "TypeError: Cannot read properties of undefined",
        "error_context": {
            "error_type": "TypeError",
            "message": "Cannot read properties of undefined (reading 'map')",
            "file_path": "src/List.jsx",
            "line": 42,
            "column": 10,
            "snippet": "items.map(i => i.title)",
        },
    }
    response = await async_client.post("/api/v1/runs", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["data"]["status"] == "failure"
    incident_id = body["data"]["incident_id"]
    assert incident_id is not None
    assert incident_id == "inc_evt_fail_001"

    # Verify incident exists in DB
    inc_doc = test_db.incidents.find_one({"incident_id": incident_id})
    assert inc_doc is not None
    assert inc_doc["error_type"] == "TypeError"
    assert inc_doc["file_path"] == "src/List.jsx"
    assert inc_doc["line"] == 42
    assert inc_doc["error_signature"].startswith("sig_TypeError_")


@pytest.mark.anyio
async def test_successful_run_no_incident(registered_project, test_db, async_client: AsyncClient):
    """Scenario 13: Successful run does not create an incident."""
    payload = {
        "event_id": "evt_success_clean",
        "project_id": registered_project,
        "command": "npm run build",
        "exit_code": 0,
        "duration_ms": 2300,
        "error_context": None,
    }
    response = await async_client.post("/api/v1/runs", json=payload)
    assert response.status_code == 201
    assert response.json()["data"]["incident_id"] is None

    # Database has 0 incidents
    assert test_db.incidents.count_documents({}) == 0


@pytest.mark.anyio
async def test_retrying_failed_run_no_duplicate_incident(
    registered_project, test_db, async_client: AsyncClient
):
    """Scenario 14: Retrying the same failed run does not duplicate its incident."""
    payload = {
        "event_id": "evt_retry_fail",
        "project_id": registered_project,
        "command": "python script.py",
        "exit_code": 1,
        "duration_ms": 150,
        "error_context": {
            "error_type": "ZeroDivisionError",
            "message": "division by zero",
            "file_path": "script.py",
            "line": 10,
        },
    }

    res1 = await async_client.post("/api/v1/runs", json=payload)
    assert res1.status_code == 201
    inc1 = res1.json()["data"]["incident_id"]

    res2 = await async_client.post("/api/v1/runs", json=payload)
    assert res2.status_code == 200
    inc2 = res2.json()["data"]["incident_id"]

    assert inc1 == inc2
    # Ensure only 1 incident exists in collection
    assert test_db.incidents.count_documents({"event_id": "evt_retry_fail"}) == 1


@pytest.mark.anyio
async def test_pagination_and_status_filtering(registered_project, async_client: AsyncClient):
    """Scenario 16: Pagination and status filtering on runs."""
    # Seed 3 success runs and 2 failure runs
    for i in range(3):
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": f"evt_succ_{i}",
                "project_id": registered_project,
                "command": f"echo {i}",
                "exit_code": 0,
                "duration_ms": 50,
            },
        )
    for i in range(2):
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": f"evt_fail_{i}",
                "project_id": registered_project,
                "command": f"fail {i}",
                "exit_code": 1,
                "duration_ms": 50,
            },
        )

    # 1. Total runs for project
    all_runs = await async_client.get(f"/api/v1/projects/{registered_project}/runs")
    assert all_runs.status_code == 200
    assert all_runs.json()["data"]["total"] == 5

    # 2. Filter by success
    succ_runs = await async_client.get(f"/api/v1/projects/{registered_project}/runs?status=success")
    assert succ_runs.status_code == 200
    assert succ_runs.json()["data"]["total"] == 3

    # 3. Filter by failure
    fail_runs = await async_client.get(f"/api/v1/projects/{registered_project}/runs?status=failure")
    assert fail_runs.status_code == 200
    assert fail_runs.json()["data"]["total"] == 2

    # 4. Pagination limits
    paged = await async_client.get(f"/api/v1/projects/{registered_project}/runs?limit=2&skip=1")
    assert paged.status_code == 200
    data = paged.json()["data"]
    assert len(data["items"]) == 2
    assert data["total"] == 5
