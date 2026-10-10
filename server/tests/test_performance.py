"""Integration tests for Phase 5: Performance Monitoring & Regression Analytics."""

from unittest.mock import patch
import pytest
from httpx import AsyncClient
from pymongo.database import Database
from pymongo.errors import PyMongoError


@pytest.mark.anyio
async def test_valid_performance_measurement_creation(async_client: AsyncClient, test_db: Database):
    """Test 1: Valid performance measurement creation persists and links correctly."""
    # 1. Setup project
    proj_resp = await async_client.post("/api/v1/projects", json={"project_id": "proj_p1", "name": "Perf Project"})
    assert proj_resp.status_code == 201

    # 2. Ingest command run
    run_resp = await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_perf_001",
            "project_id": "proj_p1",
            "command": "pytest tests/unit",
            "exit_code": 0,
            "duration_ms": 150,
        },
    )
    assert run_resp.status_code == 201

    # 3. Post performance measurement
    perf_resp = await async_client.post(
        "/api/v1/performance",
        json={
            "event_id": "evt_perf_001",
            "project_id": "proj_p1",
        },
    )
    assert perf_resp.status_code == 201
    body = perf_resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["event_id"] == "evt_perf_001"
    assert data["project_id"] == "proj_p1"
    assert data["duration_ms"] == 150
    assert data["exit_code"] == 0
    assert data["regression_status"] == "unknown"  # No baseline established yet
    assert data["command_signature"].startswith("cmd_pytest_")
    assert "pytest tests/unit" in data["command_label"]


@pytest.mark.anyio
async def test_invalid_or_negative_duration_rejected(async_client: AsyncClient, test_db: Database):
    """Test 2: Invalid or negative duration rejected with HTTP 422."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_neg", "name": "Negative Test"})
    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_neg_001",
            "project_id": "proj_neg",
            "command": "pytest",
            "exit_code": 0,
            "duration_ms": 100,
        },
    )

    resp = await async_client.post(
        "/api/v1/performance",
        json={
            "event_id": "evt_neg_001",
            "project_id": "proj_neg",
            "duration_ms": -50,
        },
    )
    assert resp.status_code == 422
    assert resp.json()["success"] is False


@pytest.mark.anyio
async def test_unknown_project_handling(async_client: AsyncClient, test_db: Database):
    """Test 3: Measurement for unknown project returns HTTP 404."""
    resp = await async_client.post(
        "/api/v1/performance",
        json={
            "event_id": "evt_unknown_proj",
            "project_id": "proj_does_not_exist",
        },
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["error"].lower()


@pytest.mark.anyio
async def test_referenced_run_not_found(async_client: AsyncClient, test_db: Database):
    """Test 4: Measurement referencing non-existent run returns HTTP 404."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_norun", "name": "No Run Project"})
    resp = await async_client.post(
        "/api/v1/performance",
        json={
            "event_id": "evt_nonexistent_run",
            "project_id": "proj_norun",
        },
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["error"].lower()


@pytest.mark.anyio
async def test_run_project_mismatch_rejection(async_client: AsyncClient, test_db: Database):
    """Test 5: Measurement with run belonging to different project returns HTTP 422."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_alpha", "name": "Project Alpha"})
    await async_client.post("/api/v1/projects", json={"project_id": "proj_beta", "name": "Project Beta"})

    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_alpha_01",
            "project_id": "proj_alpha",
            "command": "pytest",
            "exit_code": 0,
            "duration_ms": 100,
        },
    )

    resp = await async_client.post(
        "/api/v1/performance",
        json={
            "event_id": "evt_alpha_01",
            "project_id": "proj_beta",  # Mismatch!
        },
    )
    assert resp.status_code == 422
    assert "belongs to project 'proj_alpha'" in resp.json()["error"]


@pytest.mark.anyio
async def test_duplicate_event_idempotency(async_client: AsyncClient, test_db: Database):
    """Test 6: Identical retry with same event_id is idempotent."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_idem", "name": "Idempotent Project"})
    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_idem_01",
            "project_id": "proj_idem",
            "command": "npm test",
            "exit_code": 0,
            "duration_ms": 250,
        },
    )

    # First attempt: 201 Created
    r1 = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_idem_01", "project_id": "proj_idem"},
    )
    assert r1.status_code == 201
    assert r1.json()["data"]["idempotent"] is False

    # Second identical attempt: 200 OK with idempotent flag
    r2 = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_idem_01", "project_id": "proj_idem"},
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["idempotent"] is True

    # Database only contains 1 measurement
    assert test_db.performance_runs.count_documents({"event_id": "evt_idem_01"}) == 1


@pytest.mark.anyio
async def test_conflicting_duplicate_measurement_rejection(async_client: AsyncClient, test_db: Database):
    """Test 7: Reusing event_id with conflicting measurement data returns HTTP 409 Conflict."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_conf", "name": "Conflict Project"})
    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_conf_01",
            "project_id": "proj_conf",
            "command": "pytest",
            "exit_code": 0,
            "duration_ms": 100,
        },
    )

    r1 = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_conf_01", "project_id": "proj_conf", "duration_ms": 100},
    )
    assert r1.status_code == 201

    # Conflict: different duration
    r2 = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_conf_01", "project_id": "proj_conf", "duration_ms": 999},
    )
    assert r2.status_code == 409
    assert "conflict" in r2.json()["error"].lower()


@pytest.mark.anyio
async def test_baseline_creation_sufficient_samples(async_client: AsyncClient, test_db: Database):
    """Test 8: Baseline creation succeeds when sample count meets threshold."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_base", "name": "Baseline Project"})

    durations = [100, 110, 120, 130, 140]
    for i, dur in enumerate(durations):
        eid = f"evt_b_{i}"
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": eid,
                "project_id": "proj_base",
                "command": "pytest tests/api",
                "exit_code": 0,
                "duration_ms": dur,
            },
        )
        await async_client.post(
            "/api/v1/performance",
            json={"event_id": eid, "project_id": "proj_base"},
        )

    # Compute baseline (default min_samples=5)
    resp = await async_client.post(
        "/api/v1/projects/proj_base/performance/baseline",
        json={"min_samples": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "established"
    assert data["sample_count"] == 5
    assert data["baseline_duration_ms"] == 120.0
    assert data["metric"] == "median"


@pytest.mark.anyio
async def test_insufficient_samples_does_not_fabricate_baseline(async_client: AsyncClient, test_db: Database):
    """Test 9: Insufficient samples does not fabricate a baseline."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_few", "name": "Few Samples Project"})

    # Only 3 samples
    for i in range(3):
        eid = f"evt_few_{i}"
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": eid,
                "project_id": "proj_few",
                "command": "pytest",
                "exit_code": 0,
                "duration_ms": 100 + i * 10,
            },
        )
        await async_client.post(
            "/api/v1/performance",
            json={"event_id": eid, "project_id": "proj_few"},
        )

    resp = await async_client.post(
        "/api/v1/projects/proj_few/performance/baseline",
        json={"min_samples": 5},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "insufficient_data"
    assert data["baseline_duration_ms"] is None
    assert data["sample_count"] == 3
    assert data["min_samples_required"] == 5
    assert "insufficient samples" in data["message"].lower()


@pytest.mark.anyio
async def test_baseline_uses_robust_median_statistic(async_client: AsyncClient, test_db: Database):
    """Test 10: Baseline calculation uses median which is resilient against outliers."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_med", "name": "Median Project"})

    # 5 runs: 100, 105, 110, 115, and 1000 (huge outlier)
    # Mean would be 286.0; Median is 110.0!
    outlier_durations = [100, 105, 110, 115, 1000]
    for i, dur in enumerate(outlier_durations):
        eid = f"evt_med_{i}"
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": eid,
                "project_id": "proj_med",
                "command": "pytest tests/fast",
                "exit_code": 0,
                "duration_ms": dur,
            },
        )
        await async_client.post(
            "/api/v1/performance",
            json={"event_id": eid, "project_id": "proj_med"},
        )

    resp = await async_client.post(
        "/api/v1/projects/proj_med/performance/baseline",
        json={"min_samples": 5},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "established"
    assert data["baseline_duration_ms"] == 110.0
    assert data["metric"] == "median"
    assert data["mean_duration_ms"] == 286.0


@pytest.mark.anyio
async def test_normal_measurement_classification(async_client: AsyncClient, test_db: Database):
    """Test 11: Normal measurement within thresholds is classified as 'normal'."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_norm", "name": "Normal Project"})

    # Establish baseline of 200 ms with 5 runs of 200 ms
    for i in range(5):
        eid = f"evt_norm_init_{i}"
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": eid,
                "project_id": "proj_norm",
                "command": "pytest tests/core",
                "exit_code": 0,
                "duration_ms": 200,
            },
        )
        await async_client.post(
            "/api/v1/performance",
            json={"event_id": eid, "project_id": "proj_norm"},
        )

    await async_client.post("/api/v1/projects/proj_norm/performance/baseline")

    # Ingest run with 230 ms (+15% increase, +30ms increase -> below 30% and below 100ms)
    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_norm_eval",
            "project_id": "proj_norm",
            "command": "pytest tests/core",
            "exit_code": 0,
            "duration_ms": 230,
        },
    )
    resp = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_norm_eval", "project_id": "proj_norm"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["regression_status"] == "normal"
    assert data["baseline_duration_ms"] == 200.0


@pytest.mark.anyio
async def test_potential_regression_classification_above_both_thresholds(
    async_client: AsyncClient, test_db: Database
):
    """Test 12: Measurement exceeding BOTH relative (30%) and absolute (100ms) thresholds is flagged 'potential_regression'."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_regr", "name": "Regression Project"})

    # Establish baseline of 200 ms
    for i in range(5):
        eid = f"evt_regr_init_{i}"
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": eid,
                "project_id": "proj_regr",
                "command": "pytest tests/core",
                "exit_code": 0,
                "duration_ms": 200,
            },
        )
        await async_client.post(
            "/api/v1/performance",
            json={"event_id": eid, "project_id": "proj_regr"},
        )

    await async_client.post("/api/v1/projects/proj_regr/performance/baseline")

    # Ingest run with 350 ms (+75% increase > 30%, and +150ms increase > 100ms)
    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_regr_eval",
            "project_id": "proj_regr",
            "command": "pytest tests/core",
            "exit_code": 0,
            "duration_ms": 350,
        },
    )
    resp = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_regr_eval", "project_id": "proj_regr"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["regression_status"] == "potential_regression"
    assert data["baseline_duration_ms"] == 200.0


@pytest.mark.anyio
async def test_no_baseline_produces_unknown(async_client: AsyncClient, test_db: Database):
    """Test 13: Ingestion without an established baseline produces regression_status='unknown'."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_nobase", "name": "No Base Project"})
    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_nobase_01",
            "project_id": "proj_nobase",
            "command": "pytest tests/fresh",
            "exit_code": 0,
            "duration_ms": 500,
        },
    )

    resp = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_nobase_01", "project_id": "proj_nobase"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["regression_status"] == "unknown"
    assert data["baseline_duration_ms"] is None


@pytest.mark.anyio
async def test_failed_commands_not_labeled_as_performance_regressions(
    async_client: AsyncClient, test_db: Database
):
    """Test 14: Failed commands (exit_code != 0) taking longer are not flagged as potential regressions."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_fail", "name": "Fail Project"})

    # Establish baseline of 100 ms
    for i in range(5):
        eid = f"evt_f_init_{i}"
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": eid,
                "project_id": "proj_fail",
                "command": "npm test",
                "exit_code": 0,
                "duration_ms": 100,
            },
        )
        await async_client.post(
            "/api/v1/performance",
            json={"event_id": eid, "project_id": "proj_fail"},
        )

    await async_client.post("/api/v1/projects/proj_fail/performance/baseline")

    # Ingest a failed command that took 2000 ms (crashed/timed out)
    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_f_failed_run",
            "project_id": "proj_fail",
            "command": "npm test",
            "exit_code": 1,  # Non-zero!
            "duration_ms": 2000,
        },
    )
    resp = await async_client.post(
        "/api/v1/performance",
        json={"event_id": "evt_f_failed_run", "project_id": "proj_fail"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["regression_status"] == "unknown"  # NOT potential_regression!


@pytest.mark.anyio
async def test_project_performance_history_filtering_and_pagination(
    async_client: AsyncClient, test_db: Database
):
    """Test 15: Project performance history retrieval supports pagination and filtering."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_hist", "name": "Hist Project"})

    for i in range(6):
        eid = f"evt_hist_{i}"
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": eid,
                "project_id": "proj_hist",
                "command": "pytest" if i < 4 else "flake8",
                "exit_code": 0,
                "duration_ms": 100 + i * 20,
            },
        )
        await async_client.post(
            "/api/v1/performance",
            json={"event_id": eid, "project_id": "proj_hist"},
        )

    # 1. Test pagination limit=3, skip=0
    p1 = await async_client.get("/api/v1/projects/proj_hist/performance?limit=3&skip=0")
    assert p1.status_code == 200
    b1 = p1.json()["data"]
    assert len(b1["items"]) == 3
    assert b1["total"] == 6

    # 2. Test pagination limit=3, skip=3
    p2 = await async_client.get("/api/v1/projects/proj_hist/performance?limit=3&skip=3")
    assert p2.status_code == 200
    b2 = p2.json()["data"]
    assert len(b2["items"]) == 3

    # 3. Test filtering by regression status
    p3 = await async_client.get("/api/v1/projects/proj_hist/performance?regression_status=unknown")
    assert p3.status_code == 200
    assert p3.json()["data"]["total"] == 6


@pytest.mark.anyio
async def test_performance_analytics_aggregation(async_client: AsyncClient, test_db: Database):
    """Test 16: Project performance analytics computes summary and command breakdowns."""
    await async_client.post("/api/v1/projects", json={"project_id": "proj_agg", "name": "Analytics Project"})

    # Ingest 4 successful runs (100, 110, 120, 130) and 1 failed run (300)
    for i, dur in enumerate([100, 110, 120, 130]):
        eid = f"evt_agg_s_{i}"
        await async_client.post(
            "/api/v1/runs",
            json={
                "event_id": eid,
                "project_id": "proj_agg",
                "command": "pytest",
                "exit_code": 0,
                "duration_ms": dur,
            },
        )
        await async_client.post("/api/v1/performance", json={"event_id": eid, "project_id": "proj_agg"})

    await async_client.post(
        "/api/v1/runs",
        json={
            "event_id": "evt_agg_f_0",
            "project_id": "proj_agg",
            "command": "pytest",
            "exit_code": 1,
            "duration_ms": 300,
        },
    )
    await async_client.post("/api/v1/performance", json={"event_id": "evt_agg_f_0", "project_id": "proj_agg"})

    resp = await async_client.get("/api/v1/projects/proj_agg/performance/analytics")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["project_id"] == "proj_agg"
    assert data["total_measurements"] == 5
    assert data["successful_measurements"] == 4
    assert data["failed_measurements"] == 1
    assert data["average_duration_ms"] == 152.0  # (100 + 110 + 120 + 130 + 300) / 5
    assert data["median_duration_ms"] == 120.0  # sorted: [100, 110, 120, 130, 300]
    assert len(data["commands"]) == 1
    cmd = data["commands"][0]
    assert cmd["total_runs"] == 5
    assert cmd["successful_runs"] == 4
    assert cmd["failed_runs"] == 1


@pytest.mark.anyio
async def test_missing_project_returns_404(async_client: AsyncClient, test_db: Database):
    """Test 17: All performance endpoints return HTTP 404 for missing project."""
    missing = "proj_does_not_exist_404"

    r1 = await async_client.get(f"/api/v1/projects/{missing}/performance")
    assert r1.status_code == 404

    r2 = await async_client.get(f"/api/v1/projects/{missing}/performance/analytics")
    assert r2.status_code == 404

    r3 = await async_client.get(f"/api/v1/projects/{missing}/performance/baselines")
    assert r3.status_code == 404

    r4 = await async_client.post(f"/api/v1/projects/{missing}/performance/baseline")
    assert r4.status_code == 404


@pytest.mark.anyio
async def test_mongodb_failures_handled_safely(async_client: AsyncClient, test_db: Database):
    """Test 18: Database failures during measurement persistence return masked HTTP 500 envelope."""
    from unittest.mock import MagicMock
    from pymongo.errors import ConnectionFailure
    from app.db.mongo import get_database
    from app.main import app

    mock_db = MagicMock()
    mock_db.projects.find_one.return_value = {"project_id": "proj_err", "name": "Error Project"}
    mock_db.command_runs.find_one.return_value = {
        "event_id": "evt_err_01",
        "project_id": "proj_err",
        "duration_ms": 100,
        "command": "pytest",
        "exit_code": 0,
    }
    mock_db.performance_baselines.find_one.return_value = None
    mock_db.performance_runs.insert_one.side_effect = ConnectionFailure(
        "mongodb://user:secret@db.internal:27017 connection failed"
    )

    app.dependency_overrides[get_database] = lambda: mock_db
    try:
        resp = await async_client.post(
            "/api/v1/performance",
            json={"event_id": "evt_err_01", "project_id": "proj_err"},
        )
        assert resp.status_code == 500
        body = resp.json()
        assert body["success"] is False
        assert "secret" not in body["error"]
        assert "Database error occurred" in body["error"]
    finally:
        app.dependency_overrides.pop(get_database, None)
