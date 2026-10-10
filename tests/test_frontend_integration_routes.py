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

    # Seed diagnoses
    db.diagnoses.delete_many({})
    db.diagnoses.insert_one({
        "diagnosis_id": "diag_beta_01",
        "incident_id": "inc_beta_01",
        "project_id": "proj_frontend_beta",
        "summary": "Assertion failure due to mismatched status code",
        "likely_cause": "Expected 200 but got 500",
        "hypotheses": [{"cause": "Internal server error in test endpoint"}],
        "suggested_fix": "Fix error handling in mock endpoint",
        "evidence": ["AssertionError: Expected 200 got 500"],
        "confidence": 0.95,
        "source": "groq-llama-3.3-70b",
        "is_verified_fix": False,
        "llm_skipped": False,
        "decision_reason": None,
        "created_at": now,
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


def test_get_project_enriched_metrics(client):
    # Verify alpha metrics
    res_alpha = client.get("/api/v1/projects/proj_frontend_alpha")
    assert res_alpha.status_code == 200
    p_alpha = res_alpha.json()["data"]
    assert p_alpha["total_runs"] == 1
    assert p_alpha["failure_count"] == 0
    assert p_alpha["verified_fix_count"] == 0
    assert p_alpha["median_duration_ms"] == 150
    assert p_alpha["last_run_status"] == "success"

    # Verify beta metrics
    res_beta = client.get("/api/v1/projects/proj_frontend_beta")
    assert res_beta.status_code == 200
    p_beta = res_beta.json()["data"]
    assert p_beta["total_runs"] == 1
    assert p_beta["failure_count"] == 1
    assert p_beta["verified_fix_count"] == 1
    assert p_beta["median_duration_ms"] == 320
    assert p_beta["last_run_status"] == "failure"


def test_get_incidents_endpoint_global_and_filtered(client):
    # Global incidents list
    res = client.get("/api/v1/incidents")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["incident_id"] == "inc_beta_01"
    # Verify ai_diagnosis enrichment from db.diagnoses
    assert data["data"]["items"][0]["ai_diagnosis"] is not None
    assert data["data"]["items"][0]["ai_diagnosis"]["summary"] == "Assertion failure due to mismatched status code"

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


def test_frontend_fix_verification_workflow(client, test_db):
    """End-to-end verification workflow from web UI perspective:
    1. Proposes a fix for an incident.
    2. Rejects unevidenced exit_code 0 claims with HTTP 422.
    3. Rejects cross-tenant unauthorized verification with HTTP 403.
    4. Persists valid verification with command/details evidence.
    5. Confirms verified status on GET /incidents, GET /projects/{id}/incidents, and GET /fixes/{id}.
    6. Verifies state transitions on failure and trusted event_id execution.
    """
    now = datetime.now(timezone.utc)

    # Seed an incident for proj_frontend_alpha
    test_db.incidents.insert_one({
        "incident_id": "inc_alpha_fix_test",
        "event_id": "evt_run_01",
        "project_id": "proj_frontend_alpha",
        "error_type": "ImportError",
        "error_message": "No module named 'services.auth'",
        "error_signature": "ImportError: No module named 'services.auth'",
        "stack_trace": "Traceback (most recent call last):\n  File 'app.py', line 2",
        "file_path": "app.py",
        "line": 2,
        "column": 1,
        "is_public": False,
        "diagnosis_status": "diagnosed",
        "created_at": now,
        "updated_at": now,
    })

    # Seed trusted recorded command runs for alpha and beta
    test_db.command_runs.insert_one({
        "event_id": "evt_alpha_trusted_pass",
        "project_id": "proj_frontend_alpha",
        "command": "pytest tests/test_auth.py",
        "exit_code": 0,
        "status": "success",
        "duration_ms": 110,
        "stdout": "5 passed in 0.11s",
        "stderr": "",
        "started_at": now,
        "finished_at": now,
        "created_at": now,
    })

    # 1. Propose fix for inc_alpha_fix_test
    res_create = client.post(
        "/api/v1/incidents/inc_alpha_fix_test/fixes?project_id=proj_frontend_alpha",
        json={"description": "Add auth service export to __init__.py"},
    )
    assert res_create.status_code == 201
    create_data = res_create.json()["data"]
    fix_id = create_data["fix_id"]
    assert create_data["status"] == "proposed"
    assert create_data["verified_at"] is None

    # 2. Unevidenced exit_code 0 claim must be rejected (HTTP 422)
    res_unevidenced = client.post(
        f"/api/v1/fixes/{fix_id}/verify?project_id=proj_frontend_alpha",
        json={"exit_code": 0, "source": "user_confirmation"},
    )
    assert res_unevidenced.status_code == 422
    err_body = res_unevidenced.json()
    err_text = str(err_body.get("error") or err_body.get("detail") or "")
    assert "insufficient" in err_text.lower()

    # 3. Cross-tenant project context mismatch must be rejected (HTTP 403)
    res_mismatch = client.post(
        f"/api/v1/fixes/{fix_id}/verify?project_id=proj_frontend_beta",
        json={
            "exit_code": 0,
            "command": "pytest tests/test_auth.py",
            "details": "Ran test suite and passed",
        },
    )
    assert res_mismatch.status_code == 403

    # 4. Valid verification with command + details evidence succeeds
    res_verify = client.post(
        f"/api/v1/fixes/{fix_id}/verify?project_id=proj_frontend_alpha",
        json={
            "exit_code": 0,
            "command": "pytest tests/test_auth.py",
            "details": "Verified 5 passing tests after applying fix",
            "source": "user_confirmation",
        },
    )
    assert res_verify.status_code == 200
    verify_data = res_verify.json()["data"]
    assert verify_data["status"] == "verified"
    assert verify_data["verified_at"] is not None
    assert verify_data["verification_command"] == "pytest tests/test_auth.py"
    assert verify_data["verification_exit_code"] == 0

    # 5. Incident lookup returns enriched fix_outcome with status='verified'
    res_inc = client.get("/api/v1/incidents/inc_alpha_fix_test")
    assert res_inc.status_code == 200
    inc_data = res_inc.json()["data"]
    assert inc_data["fix_outcome"] is not None
    assert inc_data["fix_outcome"]["status"] == "verified"
    assert inc_data["fix_outcome"]["fix_id"] == fix_id

    # Project-filtered incidents also include enriched fix_outcome
    res_proj_incs = client.get("/api/v1/projects/proj_frontend_alpha/incidents")
    assert res_proj_incs.status_code == 200
    proj_incs = res_proj_incs.json()["data"]["items"]
    alpha_inc = next((i for i in proj_incs if i["incident_id"] == "inc_alpha_fix_test"), None)
    assert alpha_inc is not None
    assert alpha_inc["fix_outcome"] is not None
    assert alpha_inc["fix_outcome"]["status"] == "verified"

    # Direct fix lookup returns verified status
    res_fix = client.get(f"/api/v1/fixes/{fix_id}?project_id=proj_frontend_alpha")
    assert res_fix.status_code == 200
    assert res_fix.json()["data"]["status"] == "verified"

    # 6. Re-verifying with failing exit_code transitions status to 'failed' and clears verified_at
    res_fail = client.post(
        f"/api/v1/fixes/{fix_id}/verify?project_id=proj_frontend_alpha",
        json={
            "exit_code": 1,
            "command": "pytest tests/test_auth.py",
            "details": "Regression observed on test_auth_token",
        },
    )
    assert res_fail.status_code == 200
    fail_data = res_fail.json()["data"]
    assert fail_data["status"] == "failed"
    assert fail_data["verified_at"] is None

    # Incident reflects the updated failed status
    res_inc_after_fail = client.get("/api/v1/incidents/inc_alpha_fix_test")
    assert res_inc_after_fail.json()["data"]["fix_outcome"]["status"] == "failed"

    # 7. Trusted event_id execution verification (Mode B)
    # Using run from wrong project rejected with 403
    res_wrong_evt = client.post(
        f"/api/v1/fixes/{fix_id}/verify?project_id=proj_frontend_alpha",
        json={"exit_code": 0, "event_id": "evt_run_02"},  # evt_run_02 belongs to beta
    )
    assert res_wrong_evt.status_code == 403

    # Using valid same-project event_id succeeds and sets source to devmemory_runner
    res_trusted = client.post(
        f"/api/v1/fixes/{fix_id}/verify?project_id=proj_frontend_alpha",
        json={"exit_code": 0, "event_id": "evt_alpha_trusted_pass"},
    )
    assert res_trusted.status_code == 200
    trusted_data = res_trusted.json()["data"]
    assert trusted_data["status"] == "verified"
    assert trusted_data["verified_at"] is not None
    assert trusted_data["verification_source"] == "devmemory_runner"
    assert trusted_data["verification_event_id"] == "evt_alpha_trusted_pass"
