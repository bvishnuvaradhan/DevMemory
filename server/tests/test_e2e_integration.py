"""End-to-End Integration Tests for DevMemory Backend.

Validates complete multi-step team workflows across:
- Workflow A: Project and command execution (CLI integration boundary)
- Workflow B: Error diagnosis and fix outcome tracking (AI Module integration boundary)
- Workflow C: Historical memory retrieval and cross-project privacy safeguards
- Workflow D: Performance monitoring, baseline calculation, and regression classification
- Workflow E: Failure handling, error envelopes, and security safety
"""

from unittest.mock import MagicMock
import pytest
from httpx import AsyncClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure

from app.db.mongo import get_database
from app.main import app


@pytest.mark.anyio
async def test_workflow_a_project_and_command_execution(async_client: AsyncClient, test_db: Database):
    """Workflow A: Project registration, command run ingestion, duplicate prevention, and conflict detection."""
    # 1. Project Registration
    proj_resp = await async_client.post(
        "/api/v1/projects",
        json={"project_id": "proj_e2e_alpha", "name": "E2E Alpha Service", "description": "Backend integration test"},
    )
    assert proj_resp.status_code == 201
    proj_data = proj_resp.json()["data"]
    assert proj_data["project_id"] == "proj_e2e_alpha"

    # 2. Ingest successful command execution run
    run_resp = await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_e2e_a_001",
            "project_id": "proj_e2e_alpha",
            "command": "pytest tests/unit/test_auth.py",
            "exit_code": 0,
            "duration_ms": 135,
            "stdout": "5 passed in 0.14s",
            "stderr": "",
            "environment": {
                "os": "Windows 11",
                "runtime_version": "Python 3.12.3",
                "git_branch": "main",
                "git_commit": "1a2b3c4d",
            },
        },
    )
    assert run_resp.status_code == 201
    run_data = run_resp.json()["data"]
    assert run_data["event_id"] == "evt_e2e_a_001"
    assert run_data["status"] == "success"
    assert run_data["idempotent"] is False

    # 3. Retrieve run by event ID and verify associations
    get_run = await async_client.get("/api/v1/runs/evt_e2e_a_001")
    assert get_run.status_code == 200
    assert get_run.json()["data"]["project_id"] == "proj_e2e_alpha"
    assert get_run.json()["data"]["duration_ms"] == 135

    # 4. List runs for the project
    proj_runs = await async_client.get("/api/v1/projects/proj_e2e_alpha/runs")
    assert proj_runs.status_code == 200
    assert proj_runs.json()["data"]["total"] == 1
    assert proj_runs.json()["data"]["items"][0]["event_id"] == "evt_e2e_a_001"

    # 5. Idempotent duplicate submission (identical payload)
    dup_run = await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_e2e_a_001",
            "project_id": "proj_e2e_alpha",
            "command": "pytest tests/unit/test_auth.py",
            "exit_code": 0,
            "duration_ms": 135,
        },
    )
    assert dup_run.status_code == 200
    assert dup_run.json()["data"]["idempotent"] is True
    # Ensure no duplicate document in database
    assert test_db.command_runs.count_documents({"event_id": "evt_e2e_a_001"}) == 1

    # 6. Conflicting duplicate submission with different payload
    conflict_run = await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_e2e_a_001",
            "project_id": "proj_e2e_alpha",
            "command": "pytest tests/unit/test_auth.py",
            "exit_code": 1,  # Different exit code!
            "duration_ms": 999,
        },
    )
    assert conflict_run.status_code == 409
    assert "conflict" in conflict_run.json()["error"].lower()


@pytest.mark.anyio
async def test_workflow_b_error_diagnosis_and_fix_tracking(async_client: AsyncClient, test_db: Database):
    """Workflow B: Failed run ingestion, incident creation, AI diagnosis persistence, and empirical fix verification."""
    # 1. Project setup
    await async_client.post("/api/v1/projects", json={"project_id": "proj_e2e_beta", "name": "E2E Beta Service"})

    # 2. Ingest failed command execution run
    failed_run_resp = await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_e2e_b_fail_01",
            "project_id": "proj_e2e_beta",
            "command": "python worker.py",
            "exit_code": 1,
            "duration_ms": 210,
            "stdout": "",
            "stderr": "ZeroDivisionError: division by zero",
            "error_context": {
                "error_type": "ZeroDivisionError",
                "message": "division by zero in worker.py line 45",
                "file_path": "worker.py",
                "line": 45,
                "column": 12,
                "snippet": "ratio = total / count",
            },
        },
    )
    assert failed_run_resp.status_code == 201
    run_body = failed_run_resp.json()["data"]
    incident_id = run_body["incident_id"]
    assert incident_id is not None
    assert incident_id.startswith("inc_evt_e2e_b_fail_01")

    # 3. Retrieve incident details
    inc_resp = await async_client.get(f"/api/v1/incidents/{incident_id}")
    assert inc_resp.status_code == 200
    inc_data = inc_resp.json()["data"]
    assert inc_data["error_type"] == "ZeroDivisionError"
    assert inc_data["file_path"] == "worker.py"
    assert inc_data["line"] == 45

    # 4. Store AI Diagnosis (using both /diagnosis and /diagnoses routes)
    diag_resp = await async_client.post(
        f"/api/v1/incidents/{incident_id}/diagnoses",
        json={
            "summary": "The count variable evaluates to 0 when no items are processed.",
            "hypotheses": [
                {"cause": "Unchecked zero divisor", "is_observed": True, "details": "Count was 0"},
                {"cause": "Off-by-one loop boundary", "is_observed": False, "details": "Unlikely"},
            ],
            "suggested_fix": "Add count == 0 guard before division",
            "model_provider": "anthropic/claude-3-5-sonnet",
        },
    )
    assert diag_resp.status_code == 201
    diag_data = diag_resp.json()["data"]
    assert diag_data["incident_id"] == incident_id
    assert diag_data["summary"] == "The count variable evaluates to 0 when no items are processed."
    assert len(diag_data["hypotheses"]) == 2

    # Verify latest diagnosis retrieval
    latest_diag = await async_client.get(f"/api/v1/incidents/{incident_id}/diagnoses/latest")
    assert latest_diag.status_code == 200
    assert latest_diag.json()["data"]["summary"] == diag_data["summary"]

    # 5. Record proposed fix
    fix_resp = await async_client.post(
        f"/api/v1/incidents/{incident_id}/fixes",
        json={
            "description": "Add guard check: if count == 0: return 0.0",
            "diff_patch": "--- worker.py\n+++ worker.py\n@@ -45,1 +45,3 @@\n+if count == 0:\n+    return 0.0\n ratio = total / count",
            "files_modified": ["worker.py"],
            "commands_to_verify": ["python -m pytest tests/test_worker.py"],
        },
    )
    assert fix_resp.status_code == 201
    fix_data = fix_resp.json()["data"]
    fix_id = fix_data["fix_id"]
    assert fix_data["status"] == "proposed"

    # 6. State Machine Gate: verify that jumping directly from 'proposed' to 'verified' is blocked (HTTP 409)
    direct_jump = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={"status": "verified"},
    )
    assert direct_jump.status_code == 409
    assert "Invalid status transition" in direct_jump.json()["error"]

    # 7. Advance fix through state machine to 'applied' and 'verifying'
    apply_resp = await async_client.patch(f"/api/v1/fixes/{fix_id}", json={"status": "applied"})
    assert apply_resp.status_code == 200
    assert apply_resp.json()["data"]["status"] == "applied"

    verifying_resp = await async_client.patch(f"/api/v1/fixes/{fix_id}", json={"status": "verifying"})
    assert verifying_resp.status_code == 200
    assert verifying_resp.json()["data"]["status"] == "verifying"

    # 8. Anti-False-Verification Gate: from 'verifying', transitioning to 'verified' without evidence fails (HTTP 422)
    false_verify = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={"status": "verified"},
    )
    assert false_verify.status_code == 422
    assert "without supporting verification evidence" in false_verify.json()["error"]

    # 9. Complete verification with empirical automated command evidence
    verified_resp = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={
            "status": "verified",
            "verification_method": "command",
            "verification_command": "python -m pytest tests/test_worker.py",
            "verification_exit_code": 0,
            "verification_source": "ci_pipeline",
            "verification_details": "4 passed in 0.12s",
        },
    )
    assert verified_resp.status_code == 200
    v_data = verified_resp.json()["data"]
    assert v_data["status"] == "verified"
    assert v_data["verified_at"] is not None
    assert v_data["verification_exit_code"] == 0

    # 9. Verify alternative pathway: explicit user confirmation on second fix
    fix_user = await async_client.post(
        f"/api/v1/incidents/{incident_id}/fixes",
        json={"description": "Alternative fix verified by developer"},
    )
    fix_user_id = fix_user.json()["data"]["fix_id"]
    await async_client.patch(f"/api/v1/fixes/{fix_user_id}", json={"status": "verifying"})

    verified_user_resp = await async_client.patch(
        f"/api/v1/fixes/{fix_user_id}",
        json={
            "status": "verified",
            "verification_source": "user_confirmation",
            "verification_details": "Manually verified edge cases in staging environment",
        },
    )
    assert verified_user_resp.status_code == 200
    assert verified_user_resp.json()["data"]["status"] == "verified"


@pytest.mark.anyio
async def test_workflow_c_historical_memory_and_privacy(async_client: AsyncClient, test_db: Database):
    """Workflow C: Cross-project error signature matching and privacy sanitization guarantees."""
    # 1. Setup two distinct projects
    await async_client.post("/api/v1/projects", json={"project_id": "proj_internal_fin", "name": "Finance Core"})
    await async_client.post("/api/v1/projects", json={"project_id": "proj_consumer_app", "name": "Consumer App"})

    # 2. Ingest failed run in Project 1 containing sensitive tokens, passwords, and private filesystem paths
    fin_err_msg = (
        r"ConnectionError: Failed to connect to database in C:\Users\alice\private_finance\db\conn.py:90 "
        r"with token ghp_111111111111111111111111111111111111 and password SecretPass123! at 192.168.1.55:5432"
    )
    fin_run = await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_fin_fail_01",
            "project_id": "proj_internal_fin",
            "command": "python manage.py runserver",
            "exit_code": 1,
            "duration_ms": 300,
            "error_context": {
                "error_type": "ConnectionError",
                "message": fin_err_msg,
                "file_path": r"C:\Users\alice\private_finance\db\conn.py",
                "snippet": "conn = psycopg2.connect(credentials)",
            },
        },
    )
    assert fin_run.status_code == 201
    fin_inc_id = fin_run.json()["data"]["incident_id"]

    # 3. Ingest similar error in Project 2 (comparable signature)
    app_err_msg = (
        r"ConnectionError: Failed to connect to database in /home/bob/work/db/conn.py:90 "
        r"with token ghp_222222222222222222222222222222222222 and password AnotherPass999! at 10.0.0.12:5432"
    )
    app_run = await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_app_fail_01",
            "project_id": "proj_consumer_app",
            "command": "python app.py",
            "exit_code": 1,
            "duration_ms": 250,
            "error_context": {
                "error_type": "ConnectionError",
                "message": app_err_msg,
                "file_path": "/home/bob/work/db/conn.py",
                "snippet": "conn = psycopg2.connect(credentials)",
            },
        },
    )
    assert app_run.status_code == 201
    app_inc_id = app_run.json()["data"]["incident_id"]

    # 4. Perform historical memory query from Project 2
    hist_resp = await async_client.get(f"/api/v1/incidents/{app_inc_id}/history")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()["data"]

    # 5. Verify Cross-Project Partition and Privacy Safeguards
    cross_matches = hist_data["cross_project_matches"]
    assert len(cross_matches) >= 1

    matched_fin = next((m for m in cross_matches if m["incident_id"] == fin_inc_id), None)
    assert matched_fin is not None
    assert matched_fin["project_id"] == "proj_internal_fin"

    # Privacy verification: confirm sensitive values from Project 1 were completely stripped
    sanitized_msg = matched_fin["error_message"]
    assert "SuperSecretToken123" not in sanitized_msg
    assert "alice" not in sanitized_msg
    assert "192.168.1.55" not in sanitized_msg
    assert "ghp_111111111111111111111111111111111111" not in sanitized_msg

    # Confirm redaction placeholders replaced sensitive values
    assert "<USER_HOME>" in sanitized_msg or "<PATH>" in sanitized_msg
    assert "<REDACTED>" in sanitized_msg or "<TOKEN>" in sanitized_msg
    assert "<HOST:PORT>" in sanitized_msg


@pytest.mark.anyio
async def test_workflow_d_performance_monitoring_and_regressions(
    async_client: AsyncClient, test_db: Database
):
    """Workflow D: Performance ingestion, robust baseline establishment, dual-threshold regression, and aggregation."""
    # 1. Project setup
    await async_client.post("/api/v1/projects", json={"project_id": "proj_e2e_perf", "name": "Performance Benchmark"})

    # 2. Ingest 5 successful runs for comparable command (baseline requires min 5 observations)
    durations = [200, 205, 210, 215, 220]
    for i, dur in enumerate(durations):
        eid = f"evt_perf_base_{i}"
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": eid,
                "project_id": "proj_e2e_perf",
                "command": "pytest tests/e2e/test_checkout.py",
                "exit_code": 0,
                "duration_ms": dur,
            },
        )
        perf_res = await async_client.post(
            "/api/v1/performance",
            json={"event_id": eid, "project_id": "proj_e2e_perf"},
        )
        assert perf_res.status_code == 201

    # 3. Establish baseline
    base_calc = await async_client.post("/api/v1/projects/proj_e2e_perf/performance/baseline")
    assert base_calc.status_code == 200
    b_data = base_calc.json()["data"]
    assert b_data["status"] == "established"
    assert b_data["sample_count"] == 5
    assert b_data["baseline_duration_ms"] == 210.0  # Median of [200, 205, 210, 215, 220]
    assert b_data["metric"] == "median"

    # 4. Ingest normal measurement within thresholds (duration 240 ms -> +14.2% increase, +30 ms)
    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_perf_norm",
            "project_id": "proj_e2e_perf",
            "command": "pytest tests/e2e/test_checkout.py",
            "exit_code": 0,
            "duration_ms": 240,
        },
    )
    norm_res = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_perf_norm", "project_id": "proj_e2e_perf"},
    )
    assert norm_res.status_code == 201
    assert norm_res.json()["data"]["regression_status"] == "normal"
    assert norm_res.json()["data"]["baseline_duration_ms"] == 210.0

    # 5. Ingest potential regression measurement exceeding both +30% (> 273 ms) and +100 ms (> 310 ms)
    # Using 350 ms (+66.7% increase, +140 ms increase)
    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_perf_regr",
            "project_id": "proj_e2e_perf",
            "command": "pytest tests/e2e/test_checkout.py",
            "exit_code": 0,
            "duration_ms": 350,
        },
    )
    regr_res = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_perf_regr", "project_id": "proj_e2e_perf"},
    )
    assert regr_res.status_code == 201
    assert regr_res.json()["data"]["regression_status"] == "potential_regression"
    assert regr_res.json()["data"]["baseline_duration_ms"] == 210.0

    # 6. Verify failed command is NOT falsely flagged as regression
    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_perf_failed",
            "project_id": "proj_e2e_perf",
            "command": "pytest tests/e2e/test_checkout.py",
            "exit_code": 1,  # Command crashed!
            "duration_ms": 5000,
        },
    )
    fail_res = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_perf_failed", "project_id": "proj_e2e_perf"},
    )
    assert fail_res.status_code == 201
    assert fail_res.json()["data"]["regression_status"] == "unknown"

    # 7. Query project performance analytics aggregation
    analytics_resp = await async_client.get("/api/v1/projects/proj_e2e_perf/performance/analytics")
    assert analytics_resp.status_code == 200
    a_data = analytics_resp.json()["data"]
    assert a_data["total_measurements"] == 8
    assert a_data["successful_measurements"] == 7
    assert a_data["failed_measurements"] == 1
    assert a_data["potential_regressions_count"] == 1
    assert len(a_data["commands"]) == 1
    assert a_data["commands"][0]["baseline_duration_ms"] == 210.0


@pytest.mark.anyio
async def test_workflow_e_failure_handling_and_envelope_integrity(
    async_client: AsyncClient, test_db: Database
):
    """Workflow E: Input validation, missing resource handling, and database error masking."""
    # 1. Request validation failure: negative duration in RunCreate
    neg_run = await async_client.post(
        "/api/v1/runs",
        json={"event_id": "evt_bad_dur", "project_id": "proj_any", "command": "pytest", "exit_code": 0, "duration_ms": -100},
    )
    assert neg_run.status_code == 422
    env_422 = neg_run.json()
    assert env_422["success"] is False
    assert env_422["data"] is None
    assert "Validation failed" in env_422["error"]

    # 2. Missing resources return standard HTTP 404 envelope
    for endpoint in [
        "/api/v1/projects/nonexistent_project_999",
        "/api/v1/runs/nonexistent_event_999",
        "/api/v1/incidents/nonexistent_inc_999",
        "/api/v1/fixes/nonexistent_fix_999",
        "/api/v1/projects/nonexistent_project_999/analytics",
        "/api/v1/projects/nonexistent_project_999/performance",
    ]:
        res = await async_client.get(endpoint)
        assert res.status_code == 404
        env = res.json()
        assert env["success"] is False
        assert env["data"] is None
        assert "not found" in env["error"].lower()

    # 3. Database error masking: verify credentials and raw connection URIs are NEVER leaked
    mock_db = MagicMock()
    mock_db.projects.insert_one.side_effect = ConnectionFailure(
        "mongodb://app_user:SuperSecretPassword123@prod-cluster.internal:27017 connection timed out"
    )

    app.dependency_overrides[get_database] = lambda: mock_db
    try:
        err_res = await async_client.post(
            "/api/v1/projects",
            json={"project_id": "proj_fail_test", "name": "Fail Test"},
        )
        assert err_res.status_code == 500
        env_500 = err_res.json()
        assert env_500["success"] is False
        assert env_500["data"] is None
        assert env_500["error"] == "Database error occurred"
        assert "SuperSecretPassword123" not in env_500["error"]
        assert "prod-cluster" not in env_500["error"]
    finally:
        app.dependency_overrides.pop(get_database, None)
