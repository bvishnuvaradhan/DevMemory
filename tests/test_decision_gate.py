"""Comprehensive test suite for DevMemory LLM Call Decision Gate.

Validates all 7 required decision gate behaviors using a mocked LLM provider:
1. Reliable exact verified-fix hit -> zero LLM calls.
2. Reliable general-knowledge hit -> zero LLM calls.
3. Similar incident + verified resolution -> zero LLM calls.
4. Insufficient retrieval evidence -> LLM called.
5. Explicit fresh-analysis request -> LLM called.
6. Redaction failure -> zero provider calls.
7. Unverified or failed fix -> never returned as verified; LLM called.
8. Multi-tenant project isolation -> private fixes never leak or bypass across projects.
9. Audit and observability -> decision reason and llm_skipped recorded accurately.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))

from ai_engine.matching import compute_error_signature
from app.config import get_settings
from app.db.indexes import init_indexes
from app.db.mongo import get_database
from app.main import app
from app.services.ai_service import generate_and_store_incident_diagnosis
from app.services.decision_gate import DecisionReason

TEST_GATE_DB_NAME = "devmemory_decision_gate_test"


class RecordingMockLLMClient:
    """Mock LLM provider counting invocations and recording payloads."""

    def __init__(self, should_fail: bool = False, fail_message: str = "Provider failure") -> None:
        self.should_fail = should_fail
        self.fail_message = fail_message
        self.call_count = 0
        self.last_system_prompt: Optional[str] = None
        self.last_user_prompt: Optional[str] = None
        self.provider_name = "mock"
        self.model = "mock-diagnostic-v1"

    def generate_diagnosis(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        if self.should_fail:
            raise RuntimeError(self.fail_message)
        return json.dumps({
            "event_id": "test_event",
            "summary": "Mock LLM diagnostic inference completed",
            "likely_cause": "Diagnosed root cause by mock LLM",
            "hypotheses": ["Mock LLM hypothesis 1"],
            "recommended_steps": ["Mock corrective step 1", "Mock corrective step 2"],
            "evidence": ["Command output observed"],
            "uncertainty_description": "Mock diagnosis completed with full confidence",
            "verification_steps": ["Run test command to verify"],
            "fix_status": "unverified",
        })


@pytest.fixture(scope="session")
def gate_mongo_client():
    """Live MongoDB client session fixture for decision gate tests."""
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
    client.drop_database(TEST_GATE_DB_NAME)
    client.close()


@pytest.fixture(autouse=True)
def gate_test_db(gate_mongo_client):
    """Clean MongoDB collections between decision gate test runs."""
    db = gate_mongo_client[TEST_GATE_DB_NAME]
    for col in [
        "projects",
        "command_runs",
        "incidents",
        "diagnoses",
        "fix_outcomes",
        "llm_request_audits",
    ]:
        db[col].delete_many({})

    init_indexes(db)
    app.dependency_overrides[get_database] = lambda: db
    yield db
    app.dependency_overrides.pop(get_database, None)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ==============================================================================
# 1. Exact Known Error + Compatible Verified Fix -> ZERO LLM Calls
# ==============================================================================

def test_decision_gate_reliable_exact_verified_fix_zero_llm_calls(gate_test_db):
    """Verify that an exact known error with a compatible verified fix returns the verified fix with ZERO LLM calls."""
    now = datetime.now(timezone.utc)
    proj_id = "proj_gate_exact"
    gate_test_db.projects.insert_one({"project_id": proj_id, "name": "Exact Fix Proj", "created_at": now, "updated_at": now})

    cmd = "python manage.py migrate"
    err_msg = "psycopg2.OperationalError: could not connect to server: Connection refused"
    st = 'File "db.py", line 42, in get_connection\npsycopg2.OperationalError: could not connect to server: Connection refused'
    sig = compute_error_signature(err_msg, st, cmd)

    # 1. Historical precedent incident with verified fix in MongoDB
    precedent_inc_id = "inc_prec_001"
    gate_test_db.incidents.insert_one({
        "incident_id": precedent_inc_id,
        "project_id": proj_id,
        "error_type": "OperationalError",
        "error_message": err_msg,
        "error_signature": sig,
        "command": cmd,
        "stack_trace": st,
        "diagnosis_status": "diagnosed",
        "verification_status": "verified",
        "resolution_summary": "Start local PostgreSQL server via systemctl start postgresql",
        "is_public": False,
        "created_at": now,
    })
    gate_test_db.fix_outcomes.insert_one({
        "fix_id": "fix_prec_001",
        "incident_id": precedent_inc_id,
        "project_id": proj_id,
        "description": "Start local PostgreSQL server via systemctl start postgresql",
        "status": "verified",
        "verified_at": now,
        "created_at": now,
        "updated_at": now,
    })

    # 2. New incident with identical signature and error
    new_inc_id = "inc_new_001"
    gate_test_db.incidents.insert_one({
        "incident_id": new_inc_id,
        "project_id": proj_id,
        "error_type": "OperationalError",
        "error_message": err_msg,
        "error_signature": sig,
        "command": cmd,
        "stack_trace": st,
        "diagnosis_status": "pending",
        "is_public": False,
        "created_at": now,
    })

    mock_llm = RecordingMockLLMClient()

    # 3. Diagnose new incident
    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=gate_test_db,
        incident_id=new_inc_id,
        llm_client=mock_llm,
    )

    # STRICT ASSERTIONS:
    assert mock_llm.call_count == 0, "External LLM must NOT be called for exact error with compatible verified fix."
    assert diag_resp.llm_skipped is True
    assert diag_resp.decision_reason == DecisionReason.EXACT_VERIFIED_FIX.value
    assert diag_resp.is_verified_fix is True
    assert "Start local PostgreSQL server" in diag_resp.suggested_fix
    assert diag_resp.source == "memory/verified-fix"
    assert diag_resp.confidence >= 0.95


# ==============================================================================
# 2. General Knowledge Match -> ZERO LLM Calls
# ==============================================================================

def test_decision_gate_reliable_general_knowledge_hit_zero_llm_calls(gate_test_db):
    """Verify that a reliable general programming knowledge match returns stored guidance with ZERO LLM calls."""
    now = datetime.now(timezone.utc)
    proj_id = "proj_gate_gk"
    gate_test_db.projects.insert_one({"project_id": proj_id, "name": "GK Proj", "created_at": now, "updated_at": now})

    new_inc_id = "inc_gk_001"
    gate_test_db.incidents.insert_one({
        "incident_id": new_inc_id,
        "project_id": proj_id,
        "error_type": "ModuleNotFoundError",
        "error_message": "ModuleNotFoundError: No module named 'fastapi'",
        "error_signature": "mod_not_found_fastapi",
        "command": "python main.py",
        "stack_trace": 'File "main.py", line 1, in <module>\nModuleNotFoundError: No module named \'fastapi\'',
        "diagnosis_status": "pending",
        "is_public": False,
        "created_at": now,
    })

    mock_llm = RecordingMockLLMClient()

    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=gate_test_db,
        incident_id=new_inc_id,
        llm_client=mock_llm,
    )

    # STRICT ASSERTIONS:
    assert mock_llm.call_count == 0, "External LLM must NOT be called when reliable general knowledge guidance exists."
    assert diag_resp.llm_skipped is True
    assert diag_resp.decision_reason == DecisionReason.GENERAL_KNOWLEDGE_MATCH.value
    assert diag_resp.is_verified_fix is False, "General knowledge guidance is general advice, not an incident-verified fix."
    assert diag_resp.source == "knowledge_base/curated"
    assert any("pip install" in str(step) or "virtual environment" in str(step) for step in [diag_resp.suggested_fix] + [h.cause for h in diag_resp.hypotheses])


# ==============================================================================
# 3. Similar Incident + Verified Resolution -> ZERO LLM Calls
# ==============================================================================

def test_decision_gate_similar_incident_verified_resolution_zero_llm_calls(gate_test_db):
    """Verify that a similar incident with a verified resolution is reused with ZERO LLM calls."""
    now = datetime.now(timezone.utc)
    proj_id = "proj_gate_similar"
    gate_test_db.projects.insert_one({"project_id": proj_id, "name": "Similar Proj", "created_at": now, "updated_at": now})

    precedent_inc_id = "inc_prec_002"
    gate_test_db.incidents.insert_one({
        "incident_id": precedent_inc_id,
        "project_id": proj_id,
        "error_type": "ConnectionRefusedError",
        "error_message": "ConnectionRefusedError: [Errno 111] Connection refused to redis://127.0.0.1:6379/0",
        "error_signature": "redis_conn_refused_6379",
        "command": "celery -A tasks worker",
        "stack_trace": 'File "tasks.py", line 8\nConnectionRefusedError: [Errno 111] Connection refused',
        "diagnosis_status": "diagnosed",
        "verification_status": "verified",
        "resolution_summary": "Start Redis daemon via systemctl start redis-server",
        "is_public": False,
        "created_at": now,
    })
    gate_test_db.fix_outcomes.insert_one({
        "fix_id": "fix_prec_002",
        "incident_id": precedent_inc_id,
        "project_id": proj_id,
        "description": "Start Redis daemon via systemctl start redis-server",
        "status": "verified",
        "verified_at": now,
        "created_at": now,
        "updated_at": now,
    })

    # Similar but slightly varied error message
    new_inc_id = "inc_similar_001"
    gate_test_db.incidents.insert_one({
        "incident_id": new_inc_id,
        "project_id": proj_id,
        "error_type": "ConnectionRefusedError",
        "error_message": "ConnectionRefusedError: [Errno 111] Connection refused to redis://localhost:6379/0",
        "error_signature": "redis_conn_refused_localhost",
        "command": "celery -A tasks worker",
        "stack_trace": 'File "tasks.py", line 8\nConnectionRefusedError: [Errno 111] Connection refused',
        "diagnosis_status": "pending",
        "is_public": False,
        "created_at": now,
    })

    mock_llm = RecordingMockLLMClient()

    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=gate_test_db,
        incident_id=new_inc_id,
        llm_client=mock_llm,
    )

    # STRICT ASSERTIONS:
    assert mock_llm.call_count == 0, "External LLM must NOT be called for similar incident with verified resolution."
    assert diag_resp.llm_skipped is True
    assert diag_resp.decision_reason in (
        DecisionReason.SIMILAR_VERIFIED_RESOLUTION.value,
        DecisionReason.EXACT_VERIFIED_FIX.value,
    )
    assert diag_resp.is_verified_fix is True
    assert "Start Redis daemon" in diag_resp.suggested_fix
    assert diag_resp.source == "memory/verified-fix"


# ==============================================================================
# 4. Insufficient Retrieval Evidence -> LLM Called
# ==============================================================================

def test_decision_gate_insufficient_retrieval_evidence_calls_llm(gate_test_db):
    """Verify that an unfamiliar/new error with insufficient retrieval evidence calls the LLM."""
    now = datetime.now(timezone.utc)
    proj_id = "proj_gate_new"
    gate_test_db.projects.insert_one({"project_id": proj_id, "name": "New Error Proj", "created_at": now, "updated_at": now})

    new_inc_id = "inc_unfamiliar_001"
    gate_test_db.incidents.insert_one({
        "incident_id": new_inc_id,
        "project_id": proj_id,
        "error_type": "CustomAppPipelineError",
        "error_message": "CustomAppPipelineError_XZ987: delta divergence exceeded bounds [39.81 > 10.0]",
        "error_signature": "custom_delta_divergence_xz987",
        "command": "python sync_pipeline.py --mode=strict",
        "stack_trace": 'File "sync_pipeline.py", line 112\nCustomAppPipelineError_XZ987: delta divergence exceeded bounds',
        "diagnosis_status": "pending",
        "is_public": False,
        "created_at": now,
    })

    mock_llm = RecordingMockLLMClient()

    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=gate_test_db,
        incident_id=new_inc_id,
        llm_client=mock_llm,
    )

    # STRICT ASSERTIONS:
    assert mock_llm.call_count == 1, "External LLM MUST be called when existing evidence is insufficient."
    assert diag_resp.llm_skipped is False
    assert diag_resp.decision_reason in (
        DecisionReason.INSUFFICIENT_EVIDENCE.value,
        DecisionReason.AMBIGUOUS_ERROR_NEEDS_ANALYSIS.value,
    )
    assert diag_resp.is_verified_fix is False
    assert diag_resp.source == "ai_engine/mock"


# ==============================================================================
# 5. Explicit Fresh-Analysis Request -> LLM Called
# ==============================================================================

def test_decision_gate_explicit_fresh_analysis_request_calls_llm(gate_test_db):
    """Verify that explicit fresh_analysis=True bypasses normal memory reuse and calls the LLM."""
    now = datetime.now(timezone.utc)
    proj_id = "proj_gate_fresh"
    gate_test_db.projects.insert_one({"project_id": proj_id, "name": "Fresh Proj", "created_at": now, "updated_at": now})

    cmd = "python script.py"
    err_msg = "psycopg2.OperationalError: could not connect to server: Connection refused"
    st = 'File "script.py", line 5\npsycopg2.OperationalError: could not connect to server: Connection refused'
    sig = compute_error_signature(err_msg, st, cmd)

    # Seed precedent with verified fix that would normally bypass LLM
    precedent_inc_id = "inc_prec_fresh_001"
    gate_test_db.incidents.insert_one({
        "incident_id": precedent_inc_id,
        "project_id": proj_id,
        "error_type": "OperationalError",
        "error_message": err_msg,
        "error_signature": sig,
        "command": cmd,
        "stack_trace": st,
        "diagnosis_status": "diagnosed",
        "verification_status": "verified",
        "resolution_summary": "Start local PostgreSQL server",
        "is_public": False,
        "created_at": now,
    })
    gate_test_db.fix_outcomes.insert_one({
        "fix_id": "fix_prec_fresh_001",
        "incident_id": precedent_inc_id,
        "project_id": proj_id,
        "description": "Start local PostgreSQL server",
        "status": "verified",
        "verified_at": now,
        "created_at": now,
        "updated_at": now,
    })

    new_inc_id = "inc_fresh_001"
    gate_test_db.incidents.insert_one({
        "incident_id": new_inc_id,
        "project_id": proj_id,
        "error_type": "OperationalError",
        "error_message": err_msg,
        "error_signature": sig,
        "command": cmd,
        "stack_trace": st,
        "diagnosis_status": "pending",
        "is_public": False,
        "created_at": now,
    })

    mock_llm = RecordingMockLLMClient()

    # Call with explicit fresh_analysis=True
    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=gate_test_db,
        incident_id=new_inc_id,
        fresh_analysis=True,
        llm_client=mock_llm,
    )

    # STRICT ASSERTIONS:
    assert mock_llm.call_count == 1, "External LLM MUST be called when explicit fresh-analysis is requested."
    assert diag_resp.llm_skipped is False
    assert diag_resp.decision_reason == DecisionReason.FRESH_ANALYSIS_REQUESTED.value
    assert diag_resp.source == "ai_engine/mock"


# ==============================================================================
# 6. Redaction / Security Failure -> ZERO Provider Calls
# ==============================================================================

def test_decision_gate_redaction_failure_zero_provider_calls(gate_test_db):
    """Verify that an error payload containing unredacted raw secrets NEVER dispatches to provider."""
    now = datetime.now(timezone.utc)
    proj_id = "proj_gate_security"
    gate_test_db.projects.insert_one({"project_id": proj_id, "name": "Security Proj", "created_at": now, "updated_at": now})

    raw_secret = "sk-proj-SUPER_SECRET_UNREDACTED_API_KEY_1234567890"
    raw_db_conn = "mongodb://admin:super_secret_password_999@cluster0.mongodb.net/prod"

    new_inc_id = "inc_unsafe_001"
    gate_test_db.incidents.insert_one({
        "incident_id": new_inc_id,
        "project_id": proj_id,
        "error_type": "AuthenticationError",
        "error_message": f"AuthenticationError: Invalid token {raw_secret} for {raw_db_conn}",
        "error_signature": "auth_error_with_leaked_creds",
        "command": f"python run.py --secret={raw_secret}",
        "stack_trace": f'File "run.py", line 10\nAuthError with {raw_secret}',
        "diagnosis_status": "pending",
        "is_public": False,
        "created_at": now,
    })

    mock_llm = RecordingMockLLMClient()

    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=gate_test_db,
        incident_id=new_inc_id,
        llm_client=mock_llm,
    )

    # STRICT ASSERTIONS:
    assert mock_llm.call_count == 0, "Provider MUST NOT be dispatched when payload fails security verification."
    assert diag_resp.llm_skipped is True
    assert diag_resp.decision_reason == DecisionReason.REDACTION_SECURITY_FAILURE.value
    # Ensure raw secret did not leak into diagnosis output
    assert raw_secret not in diag_resp.summary
    assert raw_secret not in (diag_resp.likely_cause or "")


# ==============================================================================
# 7. Unverified or Failed Fix -> NEVER Returned as Verified; LLM Called
# ==============================================================================

def test_decision_gate_unverified_and_failed_fix_never_returned_as_verified(gate_test_db):
    """Verify that similarity alone or unverified/failed fixes are NEVER treated as proof of safe solution."""
    now = datetime.now(timezone.utc)
    proj_id = "proj_gate_unverified"
    gate_test_db.projects.insert_one({"project_id": proj_id, "name": "Unverified Fix Proj", "created_at": now, "updated_at": now})

    cmd = "python process_batch.py"
    err_msg = "CustomBatchError: batch processing failed with exit code 42"
    st = 'File "batch.py", line 55\nCustomBatchError: batch processing failed'
    sig = compute_error_signature(err_msg, st, cmd)

    # Precedent with FAILED / UNVERIFIED fix outcome
    precedent_inc_id = "inc_prec_failed_001"
    gate_test_db.incidents.insert_one({
        "incident_id": precedent_inc_id,
        "project_id": proj_id,
        "error_type": "CustomBatchError",
        "error_message": err_msg,
        "error_signature": sig,
        "command": cmd,
        "stack_trace": st,
        "diagnosis_status": "diagnosed",
        "verification_status": "failed",
        "resolution_summary": "Unproven tentative attempt",
        "is_public": False,
        "created_at": now,
    })
    gate_test_db.fix_outcomes.insert_one({
        "fix_id": "fix_failed_001",
        "incident_id": precedent_inc_id,
        "project_id": proj_id,
        "description": "Unproven tentative attempt that failed",
        "status": "failed",
        "created_at": now,
        "updated_at": now,
    })

    new_inc_id = "inc_unverified_target_001"
    gate_test_db.incidents.insert_one({
        "incident_id": new_inc_id,
        "project_id": proj_id,
        "error_type": "CustomBatchError",
        "error_message": err_msg,
        "error_signature": sig,
        "command": cmd,
        "stack_trace": st,
        "diagnosis_status": "pending",
        "is_public": False,
        "created_at": now,
    })

    mock_llm = RecordingMockLLMClient()

    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=gate_test_db,
        incident_id=new_inc_id,
        llm_client=mock_llm,
    )

    # STRICT ASSERTIONS:
    assert mock_llm.call_count == 1, "LLM MUST be called when candidate fix is unverified or failed."
    assert diag_resp.llm_skipped is False
    assert diag_resp.is_verified_fix is False, "Unverified/failed fixes must NEVER be returned as verified."
    assert diag_resp.decision_reason in (
        DecisionReason.UNVERIFIED_FIX_NEEDS_ANALYSIS.value,
        DecisionReason.INSUFFICIENT_EVIDENCE.value,
    )


# ==============================================================================
# 8. Project Isolation -> Private Fixes Never Leak or Bypass Across Projects
# ==============================================================================

def test_decision_gate_project_isolation_preserves_boundaries(gate_test_db):
    """Verify that private verified fixes from Project A do not leak to or bypass LLM for Project B."""
    now = datetime.now(timezone.utc)
    proj_a = "proj_private_a"
    proj_b = "proj_private_b"
    gate_test_db.projects.insert_one({"project_id": proj_a, "name": "Project A", "created_at": now, "updated_at": now})
    gate_test_db.projects.insert_one({"project_id": proj_b, "name": "Project B", "created_at": now, "updated_at": now})

    cmd = "python tenant_job.py"
    err_msg = "TenantDatabaseError: could not acquire tenant lock"
    st = 'File "tenant.py", line 20\nTenantDatabaseError: lock timeout'
    sig = compute_error_signature(err_msg, st, cmd)

    # Project A has a verified fix, but it is strictly PRIVATE (is_public=False)
    gate_test_db.incidents.insert_one({
        "incident_id": "inc_a_verified",
        "project_id": proj_a,
        "error_type": "TenantDatabaseError",
        "error_message": err_msg,
        "error_signature": sig,
        "command": cmd,
        "stack_trace": st,
        "diagnosis_status": "diagnosed",
        "verification_status": "verified",
        "resolution_summary": "Project A private resolution: Release lock via admin console",
        "is_public": False,
        "created_at": now,
    })
    gate_test_db.fix_outcomes.insert_one({
        "fix_id": "fix_a_001",
        "incident_id": "inc_a_verified",
        "project_id": proj_a,
        "description": "Project A private resolution: Release lock via admin console",
        "status": "verified",
        "verified_at": now,
        "created_at": now,
        "updated_at": now,
    })

    # Project B encounters identical error
    new_inc_b = "inc_b_001"
    gate_test_db.incidents.insert_one({
        "incident_id": new_inc_b,
        "project_id": proj_b,
        "error_type": "TenantDatabaseError",
        "error_message": err_msg,
        "error_signature": sig,
        "command": cmd,
        "stack_trace": st,
        "diagnosis_status": "pending",
        "is_public": False,
        "created_at": now,
    })

    mock_llm = RecordingMockLLMClient()

    diag_resp, is_new = generate_and_store_incident_diagnosis(
        db=gate_test_db,
        incident_id=new_inc_b,
        has_cross_project_read=False,  # Unauthorized cross-project read
        llm_client=mock_llm,
    )

    # STRICT ASSERTIONS:
    assert mock_llm.call_count == 1, "LLM MUST be called for Project B because Project A's private fix must not leak."
    assert diag_resp.llm_skipped is False
    assert diag_resp.is_verified_fix is False
    assert "Project A private resolution" not in (diag_resp.suggested_fix or "")


# ==============================================================================
# 9. API REST Route Integration with Decision Gate Audit
# ==============================================================================

@pytest.mark.anyio
async def test_decision_gate_api_endpoint_fresh_analysis(gate_test_db):
    """Verify that POST /api/v1/incidents/{incident_id}/diagnose?fresh_analysis=true propagates via API."""
    now = datetime.now(timezone.utc)
    proj_id = "proj_api_gate"
    gate_test_db.projects.insert_one({"project_id": proj_id, "name": "API Gate Proj", "created_at": now, "updated_at": now})

    inc_id = "inc_api_fresh_001"
    gate_test_db.incidents.insert_one({
        "incident_id": inc_id,
        "project_id": proj_id,
        "error_type": "ModuleNotFoundError",
        "error_message": "ModuleNotFoundError: No module named 'fastapi'",
        "error_signature": "mod_not_found_fastapi",
        "command": "python test.py",
        "diagnosis_status": "pending",
        "is_public": False,
        "created_at": now,
    })

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        # Normal call -> General Knowledge hit -> llm_skipped=True
        resp_normal = await client.post(f"/api/v1/incidents/{inc_id}/diagnose")
        assert resp_normal.status_code in (200, 201)
        data_normal = resp_normal.json()["data"]
        assert data_normal["llm_skipped"] is True
        assert data_normal["decision_reason"] == DecisionReason.GENERAL_KNOWLEDGE_MATCH.value

        # Fresh analysis call -> Bypasses decision gate -> llm_skipped=False
        resp_fresh = await client.post(f"/api/v1/incidents/{inc_id}/diagnose?fresh_analysis=true")
        assert resp_fresh.status_code in (200, 201)
        data_fresh = resp_fresh.json()["data"]
        assert data_fresh["llm_skipped"] is False
        assert data_fresh["decision_reason"] == DecisionReason.FRESH_ANALYSIS_REQUESTED.value
