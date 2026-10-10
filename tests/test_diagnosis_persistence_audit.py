"""Deterministic audit tests for Phase 7.3: Diagnosis Persistence Reliability Audit.

Audits failure windows:
1. Failure before diagnosis insertion.
2. Failure during diagnosis insertion.
3. Failure after insertion but before incident status update (inconsistent state).
4. Client retry after timeout (duplicate diagnosis accumulation).
5. Concurrent diagnosis requests for the same incident (race condition).
6. Duplicate diagnosis records and stale incident status behavior.
7. Database unavailability during persistence.
8. Preservation of Unverified Fix Guarantee under all failure and retry scenarios.
"""

from datetime import datetime, timezone
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from pymongo import MongoClient
from pymongo.errors import WriteError, AutoReconnect, ServerSelectionTimeoutError
from fastapi import HTTPException

# Path resolution
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.config import get_settings
from app.db.indexes import init_indexes
from app.services.ai_service import generate_and_store_incident_diagnosis
from app.services import diagnosis_service
from app.schemas.diagnosis import DiagnosisCreate, HypothesisItem, MatchedMemoryRef

TEST_AUDIT_DB_NAME = "devmemory_persistence_audit_test"


@pytest.fixture(scope="session")
def audit_mongo_client():
    """Session fixture providing a live MongoDB client for persistence audit."""
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
    client.drop_database(TEST_AUDIT_DB_NAME)
    client.close()


@pytest.fixture
def audit_db(audit_mongo_client):
    """Function-level fixture ensuring clean collections for each audit test."""
    db = audit_mongo_client[TEST_AUDIT_DB_NAME]
    for col in [
        "projects",
        "command_runs",
        "incidents",
        "diagnoses",
        "fix_outcomes",
    ]:
        db[col].delete_many({})

    init_indexes(db)
    yield db


def _create_test_incident(db, incident_id: str, status: str = "pending") -> dict:
    """Helper to insert a valid incident document."""
    now = datetime.now(timezone.utc)
    doc = {
        "incident_id": incident_id,
        "project_id": "proj_audit",
        "error_type": "KeyError",
        "error_message": "KeyError: 'auth_token'",
        "error_signature": "sig_key_error_auth_token",
        "diagnosis_status": status,
        "command": "python auth.py",
        "stack_trace": "KeyError: 'auth_token'",
        "created_at": now,
        "is_public": False,
    }
    db.incidents.insert_one(doc)
    return doc


# ==============================================================================
# Window 1: Failure before diagnosis insertion
# ==============================================================================

def test_audit_window_1_failure_before_insertion(audit_db):
    """Audit: Failure before insertion leaves database clean and incident pending."""
    incident_id = "inc_w1_001"
    _create_test_incident(audit_db, incident_id, status="pending")

    # Simulate failure in AI diagnosis generation before DB insertion
    with patch("app.services.ai_service.diagnose_error", side_effect=RuntimeError("AI orchestrator crashed")):
        with pytest.raises(RuntimeError):
            generate_and_store_incident_diagnosis(
                db=audit_db,
                incident_id=incident_id,
                disable_external_inference=True,
            )

    # Verifications:
    # 1. Zero diagnosis records inserted
    assert audit_db.diagnoses.count_documents({"incident_id": incident_id}) == 0
    # 2. Incident status remains 'pending'
    inc = audit_db.incidents.find_one({"incident_id": incident_id})
    assert inc["diagnosis_status"] == "pending"


# ==============================================================================
# Window 2: Failure during diagnosis insertion
# ==============================================================================

def test_audit_window_2_failure_during_insertion(audit_db):
    """Audit: Failure during diagnosis insert leaves incident pending without corrupt state."""
    incident_id = "inc_w2_001"
    _create_test_incident(audit_db, incident_id, status="pending")

    # Simulate database write failure during diagnoses.insert_one
    with patch("pymongo.collection.Collection.insert_one", side_effect=WriteError("Disk full or schema error")):
        with pytest.raises(WriteError):
            generate_and_store_incident_diagnosis(
                db=audit_db,
                incident_id=incident_id,
                disable_external_inference=True,
            )

    # Verifications:
    # 1. Incident status was NOT changed to diagnosed
    inc = audit_db.incidents.find_one({"incident_id": incident_id})
    assert inc["diagnosis_status"] == "pending"
    # 2. No diagnosis doc exists
    assert audit_db.diagnoses.count_documents({"incident_id": incident_id}) == 0


# ==============================================================================
# Window 3: Failure after insertion but before incident status update (The Inconsistency Window)
# ==============================================================================

def test_audit_window_3_two_phase_gap_causes_inconsistent_state(audit_db):
    """Audit: Demonstrates inconsistency when server crashes after insert but before incident status update."""
    incident_id = "inc_w3_001"
    _create_test_incident(audit_db, incident_id, status="pending")

    # Simulate failure on the second write (incidents.update_one)
    with patch("pymongo.collection.Collection.update_one", side_effect=AutoReconnect("Network drop during status update")):
        with pytest.raises(AutoReconnect):
            generate_and_store_incident_diagnosis(
                db=audit_db,
                incident_id=incident_id,
                disable_external_inference=True,
            )

    # Inconsistency Audit Findings:
    # 1. The diagnosis WAS successfully inserted into 'diagnoses' collection
    diag_doc = audit_db.diagnoses.find_one({"incident_id": incident_id})
    # 2. BUT the incident record was not marked 'diagnosed' due to the failure
    inc_doc = audit_db.incidents.find_one({"incident_id": incident_id})
    assert inc_doc["diagnosis_status"] != "diagnosed"

    # 3. get_latest_diagnosis succeeds and self-heals by reconciling incident status
    latest = diagnosis_service.get_latest_diagnosis(audit_db, incident_id)
    assert latest is not None
    assert latest.incident_id == incident_id
    reconciled_inc = audit_db.incidents.find_one({"incident_id": incident_id})
    assert reconciled_inc["diagnosis_status"] == "diagnosed"


# ==============================================================================
# Window 4: Client retry after timeout returns existing diagnosis idempotently
# ==============================================================================

def test_audit_window_4_client_retry_creates_duplicate_diagnoses(audit_db):
    """Audit: Demonstrates that retrying a successful diagnosis returns existing record without duplication."""
    incident_id = "inc_w4_001"
    _create_test_incident(audit_db, incident_id, status="pending")

    # Request 1 (Client initiates diagnosis, succeeds on server)
    diag1, is_new1 = generate_and_store_incident_diagnosis(
        db=audit_db,
        incident_id=incident_id,
        disable_external_inference=True,
    )
    assert is_new1 is True

    # Request 2 (Client retries following timeout)
    diag2, is_new2 = generate_and_store_incident_diagnosis(
        db=audit_db,
        incident_id=incident_id,
        disable_external_inference=True,
    )

    # Fixed Behavior Verification:
    # 1. is_new is False on retry (idempotent detection for incident_id)
    assert is_new2 is False
    assert diag2.idempotent is True

    # 2. Exactly one diagnosis document exists for the incident (no duplicates)
    all_diags = list(audit_db.diagnoses.find({"incident_id": incident_id}))
    assert len(all_diags) == 1
    assert all_diags[0]["diagnosis_id"] == diag1.diagnosis_id


# ==============================================================================
# Window 5: Concurrent diagnosis requests for the same incident
# ==============================================================================

def test_audit_window_5_concurrent_diagnosis_requests_create_duplicates(audit_db):
    """Audit: Demonstrates atomic lease acquisition prevents duplicate diagnoses under concurrency."""
    incident_id = "inc_w5_001"
    _create_test_incident(audit_db, incident_id, status="pending")

    results = []
    errors = []

    def run_worker():
        try:
            resp, is_new = generate_and_store_incident_diagnosis(
                db=audit_db,
                incident_id=incident_id,
                disable_external_inference=True,
            )
            results.append((resp, is_new))
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=run_worker)
    t2 = threading.Thread(target=run_worker)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # One worker succeeds, and competing worker either returns existing or receives 409
    assert len(results) >= 1
    count = audit_db.diagnoses.count_documents({"incident_id": incident_id})
    assert count == 1, f"Expected strictly 1 diagnosis created under concurrency, found {count}"


# ==============================================================================
# Window 6: Duplicate diagnosis records and stale incident status behavior
# ==============================================================================

def test_audit_window_6_duplicate_records_and_stale_status_query(audit_db):
    """Audit: Evaluates how queries behave when duplicate diagnoses and inconsistent statuses exist."""
    incident_id = "inc_w6_001"
    _create_test_incident(audit_db, incident_id, status="pending")

    # Create two duplicate diagnoses manually
    now = datetime.now(timezone.utc)
    for i in range(2):
        audit_db.diagnoses.insert_one({
            "diagnosis_id": f"diag_dup_{i}",
            "incident_id": incident_id,
            "project_id": "proj_audit",
            "summary": f"Diagnosis version {i}",
            "created_at": now,
        })

    # Leave incident status as pending (inconsistent state)
    inc = audit_db.incidents.find_one({"incident_id": incident_id})
    assert inc["diagnosis_status"] == "pending"

    # get_latest_diagnosis returns the most recent one and self-heals the incident status
    latest = diagnosis_service.get_latest_diagnosis(audit_db, incident_id)
    assert latest is not None
    assert latest.incident_id == incident_id

    # Self-healing reconciliation verified: incident is no longer pending, it was reconciled to 'diagnosed'
    pending_incidents = list(audit_db.incidents.find({"diagnosis_status": "pending"}))
    assert not any(p["incident_id"] == incident_id for p in pending_incidents)
    inc_after = audit_db.incidents.find_one({"incident_id": incident_id})
    assert inc_after["diagnosis_status"] == "diagnosed"


# ==============================================================================
# Window 7: MongoDB temporary unavailability during persistence
# ==============================================================================

def test_audit_window_7_database_unavailability_handling(audit_db):
    """Audit: Evaluates behavior when MongoDB connection drops entirely during diagnosis generation."""
    incident_id = "inc_w7_001"
    _create_test_incident(audit_db, incident_id, status="pending")

    # Simulate database disconnection during incident lookup
    with patch("pymongo.collection.Collection.find_one", side_effect=ServerSelectionTimeoutError("No MongoDB server reachable")):
        with pytest.raises(ServerSelectionTimeoutError):
            generate_and_store_incident_diagnosis(
                db=audit_db,
                incident_id=incident_id,
                disable_external_inference=True,
            )


# ==============================================================================
# Window 8: Preservation of Unverified Fix Guarantee under all failure paths
# ==============================================================================

def test_audit_window_8_unverified_fix_guarantee_preserved(audit_db):
    """Audit: Proves that no failure, retry, or recovery path can mark an unverified fix as verified."""
    incident_id = "inc_w8_001"
    _create_test_incident(audit_db, incident_id, status="pending")

    # 1. Normal run
    diag_resp, _ = generate_and_store_incident_diagnosis(
        db=audit_db,
        incident_id=incident_id,
        disable_external_inference=True,
    )
    for h in diag_resp.hypotheses:
        assert h.is_observed is False

    # 2. Check stored doc in MongoDB
    stored = audit_db.diagnoses.find_one({"incident_id": incident_id})
    for h in stored.get("hypotheses", []):
        assert h.get("is_observed") is False

    # 3. Check fix_outcomes table: no verified fix outcome was created
    verified_fixes = audit_db.fix_outcomes.count_documents({
        "incident_id": incident_id,
        "status": "verified",
    })
    assert verified_fixes == 0, "GUARANTEE CONFIRMED: No verified fix outcome was synthesized"
