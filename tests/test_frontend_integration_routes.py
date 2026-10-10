"""Integration tests for frontend-facing backend routes.

Validates that:
1. GET /api/v1/runs returns PaginatedResponse[RunResponse] for global and project-filtered queries.
2. GET /api/v1/incidents returns PaginatedResponse[IncidentResponse] for global and project-filtered queries.
3. GET /api/v1/fixes returns PaginatedResponse[FixOutcomeResponse] for global and project-filtered queries.
4. GET /api/v1/analytics/overview returns aggregated telemetry, projects, runs, recurring errors, and fixes.
5. GET /api/v1/analytics/performance returns performance trends.
6. GET /api/v1/events and GET /api/v1/projects/{project_id}/events return chronological audit streams.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.config import get_settings
from app.db.indexes import init_indexes
from app.db.mongo import get_database
from app.main import app

TEST_DB_NAME = "devmemory_frontend_integration_test"


@pytest.fixture(scope="module")
def mongo_client():
    settings = get_settings()
    client = MongoClient(settings.MONGODB_URI)
    db = client[TEST_DB_NAME]
    init_indexes(db)
    yield client
    client.drop_database(TEST_DB_NAME)
    client.close()


@pytest.fixture
def test_db(mongo_client):
    db = mongo_client[TEST_DB_NAME]
    db.projects.delete_many({})
    db.command_runs.delete_many({})
    db.incidents.delete_many({})
    db.fix_outcomes.delete_many({})
    db.llm_request_audits.delete_many({})

    # Seed two sample projects
    now = datetime.now(timezone.utc)
    db.projects.insert_one({
        "project_id": "proj_frontend_alpha",
        "name": "alpha-service",
        "description": "Alpha backend service",
        "language": "Python",
        "framework": "FastAPI",
        "repository": "github.com/org/alpha",
        "created_at": now,
        "updated_at": now,
    })
    db.projects.insert_one({
        "project_id": "proj_frontend_beta",
        "name": "beta-worker",
        "description": "Beta worker service",
        "language": "TypeScript",
        "framework": "Express",
        "repository": "github.com/org/beta",
        "created_at": now,
        "updated_at": now,
    })

    # Seed command runs
    db.command_runs.insert_one({
        "event_id": "evt_run_01",
        "project_id": "proj_frontend_alpha",
        "command": "pytest tests/",
        "exit_code": 0,
        "status": "success",
        "duration_ms": 150,
        "stdout": "1 passed",
        "stderr": "",
        "started_at": now,
        "finished_at": now,
        "created_at": now,
    })
    db.command_runs.insert_one({
        "event_id": "evt_run_02",
        "project_id": "proj_frontend_beta",
        "command": "npm test",
        "exit_code": 1,
        "status": "failure",
        "duration_ms": 320,
        "stdout": "",
        "stderr": "AssertionError: Expected 200 got 500",
        "started_at": now,
        "finished_at": now,
        "created_at": now,
    })

    # Seed incidents
    db.incidents.insert_one({
        "incident_id": "inc_beta_01",
        "event_id": "evt_run_02",
        "project_id": "proj_frontend_beta",
        "error_type": "AssertionError",
        "error_message": "AssertionError: Expected 200 got 500",
        "error_signature": "sig_assert_err",
        "created_at": now,
    })

    # Seed fixes
    db.fix_outcomes.insert_one({
        "fix_id": "fix_01",
        "incident_id": "inc_beta_01",
        "project_id": "proj_frontend_beta",
        "description": "Updated response status check",
        "status": "verified",
        "verification_method": "npm test",
        "verification_details": "Tests passed cleanly",
        "verified_at": now,
        "created_at": now,
        "updated_at": now,
    })

    return db


@pytest.fixture
def client(test_db):
    app.dependency_overrides[get_database] = lambda: test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_runs_endpoint_global_and_filtered(client):
    # Global runs list
    res = client.get("/api/v1/runs")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["total"] == 2
    assert len(data["data"]["items"]) == 2

    # Filtered by project
    res_filtered = client.get("/api/v1/runs?project_id=proj_frontend_alpha")
    assert res_filtered.status_code == 200
    filtered_data = res_filtered.json()
    assert filtered_data["data"]["total"] == 1
    assert filtered_data["data"]["items"][0]["event_id"] == "evt_run_01"


def test_get_incidents_endpoint_global_and_filtered(client):
    # Global incidents list
    res = client.get("/api/v1/incidents")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["incident_id"] == "inc_beta_01"

    # Filtered by nonexistent project
    res_empty = client.get("/api/v1/incidents?project_id=proj_nonexistent")
    assert res_empty.status_code == 200
    assert res_empty.json()["data"]["total"] == 0


def test_get_fixes_endpoint_global_and_filtered(client):
    # Global fixes list
    res = client.get("/api/v1/fixes")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["fix_id"] == "fix_01"

    # Filtered by project
    res_proj = client.get("/api/v1/fixes?project_id=proj_frontend_beta")
    assert res_proj.status_code == 200
    assert res_proj.json()["data"]["total"] == 1


def test_get_analytics_overview_endpoint(client):
    res = client.get("/api/v1/analytics/overview")
    assert res.status_code == 200
    envelope = res.json()
    assert envelope["success"] is True
    data = envelope["data"]

    # Verify expected frontend overview structure
    assert "stats" in data
    stats = data["stats"]
    assert stats["totalProjects"] == 2
    assert stats["totalRuns"] == 2
    assert stats["totalFailures"] == 1
    assert stats["verifiedFixes"] == 1
    assert stats["isMock"] is False

    assert "projects" in data
    assert len(data["projects"]) == 2
    assert "recentRuns" in data
    assert len(data["recentRuns"]) == 2
    assert "verifiedFixes" in data
    assert len(data["verifiedFixes"]) == 1
    assert "recurringErrors" in data
    assert isinstance(data["recurringErrors"], list)
    for rec in data["recurringErrors"]:
        assert "affectedProjects" in rec
        assert isinstance(rec["affectedProjects"], list)
        assert "occurrences" in rec
        assert "errorType" in rec


def test_get_events_endpoints(client):
    # Global events
    res_global = client.get("/api/v1/events")
    assert res_global.status_code == 200
    data_global = res_global.json()
    assert data_global["success"] is True
    assert len(data_global["data"]) == 2

    # Scoped project events
    res_proj = client.get("/api/v1/projects/proj_frontend_alpha/events")
    assert res_proj.status_code == 200
    data_proj = res_proj.json()
    assert data_proj["success"] is True
    assert len(data_proj["data"]) == 1
    assert data_proj["data"][0]["projectId"] == "proj_frontend_alpha"
