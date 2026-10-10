"""Tests for privacy-aware cross-project incident history retrieval."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def two_projects(test_db, async_client: AsyncClient):
    """Fixture initializing two distinct projects: Alpha and Beta."""
    res1 = await async_client.post(
        "/api/v1/projects",
        json={"name": "Project Alpha", "project_id": "proj_alpha"},
    )
    assert res1.status_code == 201

    res2 = await async_client.post(
        "/api/v1/projects",
        json={"name": "Project Beta", "project_id": "proj_beta"},
    )
    assert res2.status_code == 201

    return "proj_alpha", "proj_beta"


@pytest.mark.anyio
async def test_cross_project_history_and_self_exclusion(two_projects, async_client: AsyncClient):
    """Scenario 7 & 8: Retrieval finds matches in both same-project and cross-project, excluding current incident."""
    proj_a, proj_b = two_projects
    error_msg = "Cannot read property 'map' of undefined"

    # Incident 1 in Project A (target incident)
    res_a1 = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "TypeError",
            "error_message": error_msg,
            "file_path": "src/Components/List.jsx",
            "source_snippet": "items.map(item => item.id)",
        },
    )
    assert res_a1.status_code == 201
    target_id = res_a1.json()["data"]["incident_id"]

    # Incident 2 in Project A (same project past match)
    res_a2 = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "TypeError",
            "error_message": error_msg,
            "file_path": "src/Components/Header.jsx",
        },
    )
    assert res_a2.status_code == 201
    past_same_id = res_a2.json()["data"]["incident_id"]

    # Incident 3 in Project B (cross-project past match with private local path and snippet)
    res_b = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_b,
            "error_type": "TypeError",
            "error_message": (
                r"Cannot read property 'map' of undefined in C:\Users\alice_admin\secret_project\view.js"
            ),
            "file_path": r"C:\Users\alice_admin\secret_project\view.js",
            "source_snippet": "PRIVATE_SECRET_SNIPPET_DO_NOT_LEAK()",
        },
    )
    assert res_b.status_code == 201
    cross_id = res_b.json()["data"]["incident_id"]

    # Query history for target_id
    response = await async_client.get(f"/api/v1/incidents/{target_id}/history")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]

    assert data["current_incident_id"] == target_id

    # 1. Self-exclusion: target_id must NOT appear in same_project_matches
    same_matches = data["same_project_matches"]
    same_ids = [m["incident_id"] for m in same_matches]
    assert target_id not in same_ids
    assert past_same_id in same_ids

    # 2. Cross-project matches: cross_id from Project B must appear
    cross_matches = data["cross_project_matches"]
    cross_ids = [m["incident_id"] for m in cross_matches]
    assert cross_id in cross_ids


@pytest.mark.anyio
async def test_cross_project_privacy_protection(two_projects, async_client: AsyncClient):
    """Scenario 9: Cross-project results omit private source snippets, file paths, and local usernames."""
    proj_a, proj_b = two_projects

    # Create target incident in Project A
    res_a = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "ConnectionError",
            "error_message": "Connection refused to database",
        },
    )
    target_id = res_a.json()["data"]["incident_id"]

    # Create cross-project incident in Project B with sensitive paths and snippets
    await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_b,
            "error_type": "ConnectionError",
            "error_message": r"Connection refused to database at C:\Users\bob_secret\db.py Bearer super_secret_key_999",
            "file_path": r"C:\Users\bob_secret\db.py",
            "line": 150,
            "column": 4,
            "source_snippet": "connect_to_internal_db(password='confidential')",
        },
    )

    response = await async_client.get(f"/api/v1/incidents/{target_id}/history")
    assert response.status_code == 200
    data = response.json()["data"]

    cross_matches = data["cross_project_matches"]
    assert len(cross_matches) >= 1
    match = cross_matches[0]

    # Privacy assertions:
    # 1. source_snippet is NOT exposed on CrossProjectIncidentSummary
    assert "source_snippet" not in match
    # 2. file_path is NOT exposed on CrossProjectIncidentSummary
    assert "file_path" not in match
    # 3. Raw secret tokens and user paths are redacted from error_message
    assert "bob_secret" not in match["error_message"]
    assert "super_secret_key_999" not in match["error_message"]
    assert "<REDACTED>" in match["error_message"]


@pytest.mark.anyio
async def test_history_missing_incident_returns_404(async_client: AsyncClient):
    """Scenario 10: Querying history for non-existent incident returns HTTP 404."""
    response = await async_client.get("/api/v1/incidents/inc_does_not_exist/history")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert "not found" in body["error"].lower()
