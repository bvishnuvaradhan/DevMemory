"""Tests for MongoDB recurring-error aggregation and project summary analytics."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def analytics_project(test_db, async_client: AsyncClient):
    """Helper fixture providing an initialized project."""
    res = await async_client.post(
        "/api/v1/projects",
        json={"name": "AnalyticsApp", "project_id": "proj_analytics_test", "language": "python"},
    )
    assert res.status_code == 201
    return "proj_analytics_test"


@pytest.mark.anyio
async def test_recurring_errors_aggregation_counts_and_sorting(
    analytics_project, async_client: AsyncClient
):
    """Scenario 3 & 4: Aggregation pipeline groups by signature, counts occurrences, and sorts descending."""
    # Create 3 incidents for TypeError, 2 for ValueError, 1 for KeyError
    for i in range(3):
        await async_client.post(
            "/api/v1/incidents",
            json={
                "project_id": analytics_project,
                "error_type": "TypeError",
                "error_message": "data.map is not a function",
            },
        )
    for i in range(2):
        await async_client.post(
            "/api/v1/incidents",
            json={
                "project_id": analytics_project,
                "error_type": "ValueError",
                "error_message": "invalid integer value",
            },
        )
    await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": analytics_project,
            "error_type": "KeyError",
            "error_message": "session_id missing",
        },
    )

    # Query recurring errors
    response = await async_client.get(
        f"/api/v1/projects/{analytics_project}/analytics/recurring?limit=10"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]

    assert data["total_groups"] == 3
    items = data["items"]
    assert len(items) == 3

    # Ranked highest occurrence first
    assert items[0]["error_type"] == "TypeError"
    assert items[0]["occurrence_count"] == 3

    assert items[1]["error_type"] == "ValueError"
    assert items[1]["occurrence_count"] == 2

    assert items[2]["error_type"] == "KeyError"
    assert items[2]["occurrence_count"] == 1


@pytest.mark.anyio
async def test_recurring_errors_limit_bounding(analytics_project, async_client: AsyncClient):
    """Scenario 4: Limit parameter bounds aggregation output."""
    for err in ["TypeError", "ValueError", "KeyError", "IndexError"]:
        await async_client.post(
            "/api/v1/incidents",
            json={"project_id": analytics_project, "error_type": err, "error_message": f"{err} unique occurrence"},
        )

    response = await async_client.get(
        f"/api/v1/projects/{analytics_project}/analytics/recurring?limit=2"
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["items"]) == 2
    assert data["total_groups"] == 4


@pytest.mark.anyio
async def test_recurring_errors_unknown_project(async_client: AsyncClient):
    """Scenario 5: Unknown project returns HTTP 404."""
    response = await async_client.get("/api/v1/projects/proj_ghost_404/analytics/recurring")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert "not found" in body["error"].lower()


@pytest.mark.anyio
async def test_recurring_errors_empty_project(analytics_project, async_client: AsyncClient):
    """Scenario 6: Project without incidents returns empty list with total_groups 0."""
    response = await async_client.get(
        f"/api/v1/projects/{analytics_project}/analytics/recurring"
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["items"] == []
    assert data["total_groups"] == 0


@pytest.mark.anyio
async def test_project_analytics_summary_metrics(analytics_project, async_client: AsyncClient):
    """Scenario 11: Project summary analytics accurately calculates runs, incidents, and duration."""
    # Ingest 2 successful runs (100ms, 200ms -> avg 150)
    for i, dur in enumerate([100, 200]):
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": f"evt_stat_s_{i}",
                "project_id": analytics_project,
                "command": "test",
                "exit_code": 0,
                "duration_ms": dur,
            },
        )

    # Ingest 2 failed runs (300ms, 400ms) with incidents
    for i, dur in enumerate([300, 400]):
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": f"evt_stat_f_{i}",
                "project_id": analytics_project,
                "command": "test",
                "exit_code": 1,
                "duration_ms": dur,
                "error_context": {
                    "error_type": "RuntimeError",
                    "message": "system crashed",
                },
            },
        )

    response = await async_client.get(f"/api/v1/projects/{analytics_project}/analytics")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    stats = body["data"]

    assert stats["project_id"] == analytics_project
    assert stats["total_runs"] == 4
    assert stats["successful_runs"] == 2
    assert stats["failed_runs"] == 2
    assert stats["total_incidents"] == 2
    assert stats["distinct_error_signatures"] == 1
    assert stats["recent_incidents_24h"] == 2
    # Avg duration = (100 + 200 + 300 + 400) / 4 = 250ms
    assert stats["average_duration_ms"] == 250
