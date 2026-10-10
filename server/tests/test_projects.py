"""Tests for project registration and retrieval endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_create_project_success(test_db, async_client: AsyncClient):
    """Scenario 1: Successful project registration returns 201 and envelope."""
    payload = {
        "name": "E-Commerce Frontend",
        "project_id": "proj_ecommerce",
        "language": "typescript",
        "settings": {"framework": "react"},
    }
    response = await async_client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201

    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    data = body["data"]
    assert data["project_id"] == "proj_ecommerce"
    assert data["name"] == "E-Commerce Frontend"
    assert data["language"] == "typescript"
    assert data["settings"] == {"framework": "react"}
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.anyio
async def test_create_project_auto_id(test_db, async_client: AsyncClient):
    """Registering a project without project_id automatically generates one."""
    payload = {"name": "Payment Service"}
    response = await async_client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201

    body = response.json()
    assert body["success"] is True
    assert body["data"]["project_id"].startswith("proj_payment_service_")


@pytest.mark.anyio
async def test_create_project_duplicate(test_db, async_client: AsyncClient):
    """Scenario 2: Duplicate project registration returns 409 Conflict."""
    payload = {"name": "Auth Service", "project_id": "proj_auth"}
    res1 = await async_client.post("/api/v1/projects", json=payload)
    assert res1.status_code == 201

    res2 = await async_client.post("/api/v1/projects", json=payload)
    assert res2.status_code == 409
    body = res2.json()
    assert body["success"] is False
    assert "already exists" in body["error"]


@pytest.mark.anyio
async def test_get_project_success(test_db, async_client: AsyncClient):
    """Scenario 3: Project retrieval returns existing project details."""
    await async_client.post(
        "/api/v1/projects",
        json={"name": "Analytics Service", "project_id": "proj_analytics"},
    )

    response = await async_client.get("/api/v1/projects/proj_analytics")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["project_id"] == "proj_analytics"
    assert body["data"]["name"] == "Analytics Service"


@pytest.mark.anyio
async def test_get_project_not_found(test_db, async_client: AsyncClient):
    """Scenario 4: Unknown project returns HTTP 404."""
    response = await async_client.get("/api/v1/projects/non_existent_proj")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert "not found" in body["error"].lower()


@pytest.mark.anyio
async def test_list_projects_pagination(test_db, async_client: AsyncClient):
    """Pagination on project listing."""
    for i in range(5):
        await async_client.post(
            "/api/v1/projects",
            json={"name": f"Service {i}", "project_id": f"proj_srv_{i}"},
        )

    response = await async_client.get("/api/v1/projects?limit=2&skip=1")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["skip"] == 1
