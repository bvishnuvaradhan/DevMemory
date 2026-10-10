"""Tests for incident creation, retrieval, and project filtering."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def registered_project(test_db, async_client: AsyncClient):
    """Helper fixture providing an initialized project."""
    res = await async_client.post(
        "/api/v1/projects",
        json={"name": "BackendService", "project_id": "proj_backend", "language": "python"},
    )
    assert res.status_code == 201
    return "proj_backend"


@pytest.mark.anyio
async def test_create_incident_direct(registered_project, async_client: AsyncClient):
    """Explicitly register an incident via POST /api/v1/incidents."""
    payload = {
        "project_id": registered_project,
        "event_id": "evt_direct_001",
        "error_type": "KeyError",
        "error_message": "'user_id' not found in session",
        "file_path": "services/auth.py",
        "line": 88,
        "column": 12,
        "source_snippet": "session['user_id']",
    }
    response = await async_client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["project_id"] == registered_project
    assert data["error_type"] == "KeyError"
    assert data["incident_id"] == "inc_evt_direct_001"
    assert data["error_signature"].startswith("sig_KeyError_")
    assert data["diagnosis_status"] == "pending"


@pytest.mark.anyio
async def test_incident_retrieval_and_filtering(registered_project, async_client: AsyncClient):
    """Scenario 15: Incident retrieval by ID and project filtering."""
    # Register 2 incidents
    res1 = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": registered_project,
            "error_type": "ValueError",
            "error_message": "invalid literal for int() with base 10: 'abc'",
        },
    )
    assert res1.status_code == 201
    inc1_id = res1.json()["data"]["incident_id"]

    res2 = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": registered_project,
            "error_type": "IndexError",
            "error_message": "list index out of range",
        },
    )
    assert res2.status_code == 201

    # 1. Retrieve single incident by ID
    get_res = await async_client.get(f"/api/v1/incidents/{inc1_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["incident_id"] == inc1_id
    assert get_res.json()["data"]["error_type"] == "ValueError"

    # 2. Unknown incident returns 404
    not_found_res = await async_client.get("/api/v1/incidents/inc_non_existent")
    assert not_found_res.status_code == 404
    assert "not found" in not_found_res.json()["error"].lower()

    # 3. List incidents for project
    list_res = await async_client.get(f"/api/v1/projects/{registered_project}/incidents")
    assert list_res.status_code == 200
    list_data = list_res.json()["data"]
    assert list_data["total"] == 2
    assert len(list_data["items"]) == 2
