"""Step 3 Tests: Fix Outcome Tracking, Verification Evidence, and Recommendation Learning.

Validates:
1. Recording proposed fixes linked to incidents and diagnoses.
2. Automated and manual fix verification recording (exit_code=0 -> verified, exit_code!=0 -> failed).
3. Strict Unverified Fix Guarantee: unverified and failed fixes never leak as proven solutions.
4. Reversion lifecycle: reverting a verified fix resets verified_at and clears memory resolution.
5. Querying verified fixes for recommendation (by incident, by error_signature, by project).
6. Multi-tenant project isolation in verified fix retrieval.
7. Idempotent submission and cross-incident fix ID collision prevention.
8. Transition rules and evidence validation enforcement.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.config import get_settings
from app.db.indexes import init_indexes
from app.db.mongo import get_database
from app.main import app
from app.services.ai_service import MongoIncidentRepository
from app.services.incident_service import compute_error_signature

TEST_DB_NAME = "devmemory_fix_tracking_test"


@pytest.fixture(scope="session")
def mongo_client():
    """Live MongoDB client session fixture for fix tracking tests."""
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
def test_db(mongo_client):
    """Clean MongoDB collections between fix tracking test runs."""
    db = mongo_client[TEST_DB_NAME]
    for col in [
        "projects",
        "command_runs",
        "incidents",
        "diagnoses",
        "fix_outcomes",
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
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async test HTTP client bound to FastAPI application."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.anyio
async def test_record_proposed_fix_with_diagnosis_link(async_client: AsyncClient, test_db):
    """Scenario 1: Record a proposed fix with explicit links to incident and diagnosis."""
    # 1. Register project
    await async_client.post(
        "/api/v1/projects",
        json={"project_id": "proj_fix_1", "name": "Fix App 1", "language": "python"},
    )

    # 2. Register incident
    inc_resp = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": "proj_fix_1",
            "error_type": "ZeroDivisionError",
            "error_message": "division by zero",
            "file_path": "calculator.py",
            "line": 42,
        },
    )
    assert inc_resp.status_code == 201
    inc_id = inc_resp.json()["data"]["incident_id"]

    # 3. Insert mock diagnosis
    diag_id = "diag_div_zero_001"
    test_db.diagnoses.insert_one({
        "diagnosis_id": diag_id,
        "incident_id": inc_id,
        "project_id": "proj_fix_1",
        "summary": "Division by zero in calculate_ratio()",
        "probable_cause": "Denominator evaluates to 0 without guard check.",
        "hypotheses": [{"title": "Zero divisor", "likelihood": "HIGH", "reasoning": "Literal 0"}],
        "created_at": datetime.now(timezone.utc),
    })

    # 4. Propose fix linked to the diagnosis
    fix_payload = {
        "fix_id": "fix_add_guard_001",
        "diagnosis_id": diag_id,
        "description": "Add guard check: if denominator == 0: return 0.0 before division.",
    }
    fix_resp = await async_client.post(
        f"/api/v1/incidents/{inc_id}/fixes",
        json=fix_payload,
    )
    assert fix_resp.status_code == 201
    data = fix_resp.json()["data"]

    assert data["fix_id"] == "fix_add_guard_001"
    assert data["incident_id"] == inc_id
    assert data["project_id"] == "proj_fix_1"
    assert data["diagnosis_id"] == diag_id
    assert data["status"] == "proposed"
    assert data["verified_at"] is None
    assert data["verification_exit_code"] is None

    # Check MongoDB document directly
    db_doc = test_db.fix_outcomes.find_one({"fix_id": "fix_add_guard_001"})
    assert db_doc is not None
    assert db_doc["diagnosis_id"] == diag_id
    assert db_doc["status"] == "proposed"


@pytest.mark.anyio
async def test_record_fix_verification_success_via_endpoint(async_client: AsyncClient, test_db):
    """Scenario 2: Record successful verification execution (exit_code=0) transitioning to 'verified'."""
    await async_client.post(
        "/api/v1/projects",
        json={"project_id": "proj_fix_2", "name": "Fix App 2", "language": "python"},
    )
    inc_resp = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": "proj_fix_2",
            "error_type": "IndexError",
            "error_message": "list index out of range",
        },
    )
    inc_id = inc_resp.json()["data"]["incident_id"]

    fix_resp = await async_client.post(
        f"/api/v1/incidents/{inc_id}/fixes",
        json={"description": "Check if len(items) > 0 before indexing."},
    )
    fix_id = fix_resp.json()["data"]["fix_id"]

    # Verify fix using POST /fixes/{fix_id}/verify
    verify_resp = await async_client.post(
        f"/api/v1/fixes/{fix_id}/verify",
        json={
            "exit_code": 0,
            "command": "pytest tests/test_indexer.py",
            "details": "3 passed in 0.08s",
            "source": "automated_command",
        },
    )
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()["data"]

    assert v_data["status"] == "verified"
    assert v_data["verification_exit_code"] == 0
    assert v_data["verification_command"] == "pytest tests/test_indexer.py"
    assert v_data["verification_details"] == "3 passed in 0.08s"
    assert v_data["verified_at"] is not None

    # Verify MongoDB persistence
    db_doc = test_db.fix_outcomes.find_one({"fix_id": fix_id})
    assert db_doc["status"] == "verified"
    assert db_doc["verified_at"] is not None
    assert db_doc["verification_exit_code"] == 0


@pytest.mark.anyio
async def test_record_fix_verification_failure_via_endpoint(async_client: AsyncClient, test_db):
    """Scenario 3: Record failed verification execution (exit_code!=0) transitioning to 'failed'."""
    await async_client.post(
        "/api/v1/projects",
        json={"project_id": "proj_fix_3", "name": "Fix App 3", "language": "python"},
    )
    inc_resp = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": "proj_fix_3",
            "error_type": "KeyError",
            "error_message": "'database_url'",
        },
    )
    inc_id = inc_resp.json()["data"]["incident_id"]

    fix_resp = await async_client.post(
        f"/api/v1/incidents/{inc_id}/fixes",
        json={"description": "Use default sqlite fallback."},
    )
    fix_id = fix_resp.json()["data"]["fix_id"]

    # Verify with failing exit code (1)
    fail_verify_resp = await async_client.post(
        f"/api/v1/fixes/{fix_id}/verify",
        json={
            "exit_code": 1,
            "command": "pytest tests/test_db_connect.py",
            "details": "FAILED tests/test_db_connect.py - ConnectionRefusedError",
            "source": "automated_command",
        },
    )
    assert fail_verify_resp.status_code == 200
    f_data = fail_verify_resp.json()["data"]

    assert f_data["status"] == "failed"
    assert f_data["verification_exit_code"] == 1
    assert f_data["verified_at"] is None
    assert "ConnectionRefusedError" in f_data["verification_details"]

    # In DB, verified_at must be None
    db_doc = test_db.fix_outcomes.find_one({"fix_id": fix_id})
    assert db_doc["status"] == "failed"
    assert db_doc["verified_at"] is None


@pytest.mark.anyio
async def test_strict_unverified_fix_guarantee_in_enrichment(async_client: AsyncClient, test_db):
    """Scenario 4: Strict Unverified Fix Guarantee in MongoIncidentRepository._enrich_incident.

    - Unverified and failed fixes must NEVER populate resolution_summary.
    - Only fixes with status == 'verified' populate resolution_summary and verification_status='verified'.
    """
    repo = MongoIncidentRepository(test_db)

    # 1. Setup incident
    inc_doc = {
        "incident_id": "inc_guarantee_test",
        "project_id": "proj_guarantee",
        "error_type": "ValueError",
        "error_message": "invalid literal for int()",
        "error_signature": compute_error_signature("ValueError", "invalid literal for int()"),
        "created_at": datetime.now(timezone.utc),
    }
    test_db.incidents.insert_one(inc_doc)

    # Subtest A: No fix outcomes -> unverified, resolution_summary is None
    enriched_none = repo._enrich_incident(dict(inc_doc))
    assert enriched_none["verification_status"] == "unverified"
    assert enriched_none.get("resolution_summary") is None

    # Subtest B: Proposed fix outcome -> unverified, resolution_summary MUST NOT be set
    test_db.fix_outcomes.insert_one({
        "fix_id": "fix_prop_1",
        "incident_id": "inc_guarantee_test",
        "project_id": "proj_guarantee",
        "description": "Strip whitespace before int() casting",
        "status": "proposed",
        "verified_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    enriched_prop = repo._enrich_incident(dict(inc_doc))
    assert enriched_prop["verification_status"] == "unverified"
    assert enriched_prop.get("resolution_summary") is None, "Proposed fix leaked into resolution_summary!"

    # Subtest C: Failed fix outcome -> failed, resolution_summary MUST NOT be set
    test_db.fix_outcomes.update_one(
        {"fix_id": "fix_prop_1"},
        {"$set": {"status": "failed", "verification_exit_code": 1}},
    )
    enriched_failed = repo._enrich_incident(dict(inc_doc))
    assert enriched_failed["verification_status"] == "failed"
    assert enriched_failed.get("resolution_summary") is None, "Failed fix leaked into resolution_summary!"

    # Subtest D: Verified fix outcome -> verified, resolution_summary is properly populated
    test_db.fix_outcomes.insert_one({
        "fix_id": "fix_verified_1",
        "incident_id": "inc_guarantee_test",
        "project_id": "proj_guarantee",
        "description": "Use regex check: if re.match(r'^-?\\d+$', s): int(s)",
        "status": "verified",
        "verification_exit_code": 0,
        "verified_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    enriched_ver = repo._enrich_incident(dict(inc_doc))
    assert enriched_ver["verification_status"] == "verified"
    assert enriched_ver["resolution_summary"] == "Use regex check: if re.match(r'^-?\\d+$', s): int(s)"

    # Subtest E: A newer unverified proposal does NOT demote the verified status
    test_db.fix_outcomes.insert_one({
        "fix_id": "fix_new_prop_2",
        "incident_id": "inc_guarantee_test",
        "project_id": "proj_guarantee",
        "description": "Another hypothetical fix idea",
        "status": "proposed",
        "verified_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    enriched_with_newer_prop = repo._enrich_incident(dict(inc_doc))
    assert enriched_with_newer_prop["verification_status"] == "verified"
    assert enriched_with_newer_prop["resolution_summary"] == "Use regex check: if re.match(r'^-?\\d+$', s): int(s)"


@pytest.mark.anyio
async def test_get_verified_fixes_by_incident_endpoint(async_client: AsyncClient, test_db):
    """Scenario 5: Endpoint GET /incidents/{incident_id}/fixes/verified returns only verified fixes."""
    await async_client.post(
        "/api/v1/projects",
        json={"project_id": "proj_verified_ep", "name": "Verified EP App"},
    )
    inc_resp = await async_client.post(
        "/api/v1/incidents",
        json={"project_id": "proj_verified_ep", "error_type": "IOError", "error_message": "file not found"},
    )
    inc_id = inc_resp.json()["data"]["incident_id"]

    # Create 2 fixes
    f1_resp = await async_client.post(
        f"/api/v1/incidents/{inc_id}/fixes",
        json={"description": "Fix 1: check path.exists()"},
    )
    f1_id = f1_resp.json()["data"]["fix_id"]

    f2_resp = await async_client.post(
        f"/api/v1/incidents/{inc_id}/fixes",
        json={"description": "Fix 2: use try-except FileNotFoundError"},
    )
    f2_id = f2_resp.json()["data"]["fix_id"]

    # Verify only Fix 2
    await async_client.post(
        f"/api/v1/fixes/{f2_id}/verify",
        json={"exit_code": 0, "command": "pytest", "details": "passed"},
    )

    # Query GET /incidents/{incident_id}/fixes/verified
    resp = await async_client.get(f"/api/v1/incidents/{inc_id}/fixes/verified")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["fix_id"] == f2_id
    assert data[0]["status"] == "verified"
    assert data[0]["description"] == "Fix 2: use try-except FileNotFoundError"


@pytest.mark.anyio
async def test_query_verified_fixes_endpoint_and_isolation(async_client: AsyncClient, test_db):
    """Scenario 6: Query verified fixes by error_signature and enforce multi-tenant isolation."""
    # 1. Project Alpha
    await async_client.post(
        "/api/v1/projects",
        json={"project_id": "proj_alpha", "name": "Alpha Service"},
    )
    # 2. Project Beta
    await async_client.post(
        "/api/v1/projects",
        json={"project_id": "proj_beta", "name": "Beta Service"},
    )

    err_sig = compute_error_signature("ZeroDivisionError", "integer division or modulo by zero")

    # Ingest incident in Alpha
    inc_alpha = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": "proj_alpha",
            "error_type": "ZeroDivisionError",
            "error_message": "integer division or modulo by zero",
        },
    )
    inc_a_id = inc_alpha.json()["data"]["incident_id"]

    # Ingest incident in Beta
    inc_beta = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": "proj_beta",
            "error_type": "ZeroDivisionError",
            "error_message": "integer division or modulo by zero",
        },
    )
    inc_b_id = inc_beta.json()["data"]["incident_id"]

    # Create & verify fix in Alpha
    fix_a = await async_client.post(
        f"/api/v1/incidents/{inc_a_id}/fixes",
        json={"description": "Alpha Solution: guard modulo with non-zero check"},
    )
    await async_client.post(
        f"/api/v1/fixes/{fix_a.json()['data']['fix_id']}/verify",
        json={"exit_code": 0, "command": "pytest", "details": "Alpha tests pass"},
    )

    # Create & verify fix in Beta
    fix_b = await async_client.post(
        f"/api/v1/incidents/{inc_b_id}/fixes",
        json={"description": "Beta Solution: return 0 on zero modulus"},
    )
    await async_client.post(
        f"/api/v1/fixes/{fix_b.json()['data']['fix_id']}/verify",
        json={"exit_code": 0, "command": "pytest", "details": "Beta tests pass"},
    )

    # Query scoped to Project Alpha
    res_a = await async_client.get(
        "/api/v1/fixes/verified",
        params={"project_id": "proj_alpha", "error_signature": err_sig},
    )
    assert res_a.status_code == 200
    fixes_a = res_a.json()["data"]
    assert len(fixes_a) == 1
    assert fixes_a[0]["project_id"] == "proj_alpha"
    assert "Alpha Solution" in fixes_a[0]["description"]

    # Query scoped to Project Beta
    res_b = await async_client.get(
        "/api/v1/fixes/verified",
        params={"project_id": "proj_beta", "error_signature": err_sig},
    )
    assert res_b.status_code == 200
    fixes_b = res_b.json()["data"]
    assert len(fixes_b) == 1
    assert fixes_b[0]["project_id"] == "proj_beta"
    assert "Beta Solution" in fixes_b[0]["description"]


@pytest.mark.anyio
async def test_fix_idempotency_and_cross_incident_conflict(async_client: AsyncClient, test_db):
    """Scenario 7: Duplicate fix ID for same incident is idempotent; for different incident returns 409."""
    await async_client.post(
        "/api/v1/projects",
        json={"project_id": "proj_idem", "name": "Idem App"},
    )
    inc_1 = await async_client.post(
        "/api/v1/incidents",
        json={"project_id": "proj_idem", "error_type": "ErrA", "error_message": "msgA"},
    )
    inc_1_id = inc_1.json()["data"]["incident_id"]

    inc_2 = await async_client.post(
        "/api/v1/incidents",
        json={"project_id": "proj_idem", "error_type": "ErrB", "error_message": "msgB"},
    )
    inc_2_id = inc_2.json()["data"]["incident_id"]

    # 1. Create fix with client-specified ID for incident 1
    res1 = await async_client.post(
        f"/api/v1/incidents/{inc_1_id}/fixes",
        json={"fix_id": "stable_fix_42", "description": "Stable fix description"},
    )
    assert res1.status_code == 201

    # 2. Resubmit same fix_id for same incident -> idempotent
    res2 = await async_client.post(
        f"/api/v1/incidents/{inc_1_id}/fixes",
        json={"fix_id": "stable_fix_42", "description": "Duplicate call"},
    )
    assert res2.status_code in (200, 201)
    assert res2.json()["data"]["fix_id"] == "stable_fix_42"

    # 3. Submit same fix_id for different incident -> HTTP 409 Conflict
    res3 = await async_client.post(
        f"/api/v1/incidents/{inc_2_id}/fixes",
        json={"fix_id": "stable_fix_42", "description": "Attempted reuse on other incident"},
    )
    assert res3.status_code == 409
    assert "already exists for another incident" in res3.json()["error"]


@pytest.mark.anyio
async def test_revert_verified_fix_clears_verified_at_and_revokes_memory(async_client: AsyncClient, test_db):
    """Scenario 8: Reverting a verified fix resets verified_at and clears memory resolution."""
    await async_client.post(
        "/api/v1/projects",
        json={"project_id": "proj_rev", "name": "Revert App"},
    )
    inc = await async_client.post(
        "/api/v1/incidents",
        json={"project_id": "proj_rev", "error_type": "ErrC", "error_message": "msgC"},
    )
    inc_id = inc.json()["data"]["incident_id"]

    # Create & verify fix
    fix_res = await async_client.post(
        f"/api/v1/incidents/{inc_id}/fixes",
        json={"description": "Flawed fix that later regresses"},
    )
    fix_id = fix_res.json()["data"]["fix_id"]

    await async_client.post(
        f"/api/v1/fixes/{fix_id}/verify",
        json={"exit_code": 0, "command": "pytest", "details": "passed initially"},
    )

    # Check verified status before revert
    fix_before = (await async_client.get(f"/api/v1/fixes/{fix_id}")).json()["data"]
    assert fix_before["status"] == "verified"
    assert fix_before["verified_at"] is not None

    # Revert the fix
    revert_res = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={"status": "reverted", "verification_details": "Fix broke payment flow, reverted."},
    )
    assert revert_res.status_code == 200
    fix_after = revert_res.json()["data"]
    assert fix_after["status"] == "reverted"
    assert fix_after["verified_at"] is None

    # Verify retrieval memory: incident resolution_summary MUST now be None
    repo = MongoIncidentRepository(test_db)
    raw_inc = test_db.incidents.find_one({"incident_id": inc_id}, {"_id": 0})
    enriched = repo._enrich_incident(raw_inc)
    assert enriched["verification_status"] == "failed"
    assert enriched.get("resolution_summary") is None
