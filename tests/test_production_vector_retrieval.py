"""Integration tests for Atlas Vector Search, Production Retrieval, and AI Memory Integration.

Validates:
1. Atlas Vector Search index inspection, readiness, and fallback reporting.
2. ProductionMongoVectorSearchAdapter execution with in-memory cosine fallback resilience.
3. Strict multi-tenant project isolation (private incidents never leak across projects).
4. Public cross-project precedents and project ID disclosure policies.
5. Strict Unverified Fix Guarantee: unverified/failed fixes never leak resolution summaries.
6. Vector hygiene: empty, zero, non-finite, and malformed vectors safely return empty lists.
7. REST API endpoints: GET /vector-search/status and POST /search/vector.
8. End-to-end AI diagnosis orchestration with hybrid vector search integration.
"""

import math
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from pymongo.database import Database

from ai_engine.schemas import FixVerificationStatus
from app.db.mongo import mongo_manager
from app.main import app
from app.services.ai_service import generate_and_store_incident_diagnosis
from app.services.embedding_service import (
    ProductionMongoVectorSearchAdapter,
    get_atlas_vector_index_status,
    vector_search_incidents,
)
from app.utils.signature import compute_error_signature


@pytest.fixture(scope="module")
def test_db() -> Database:
    """Fixture providing active database connection."""
    mongo_manager.connect()
    db = mongo_manager.get_db()
    yield db


@pytest.fixture(scope="module")
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    with TestClient(app) as test_client:
        yield test_client


def _make_unit_vector(dim: int, active_idx: int) -> list[float]:
    """Create a unit vector with 1.0 at active_idx and 0.0 elsewhere."""
    vec = [0.0] * dim
    vec[active_idx % dim] = 1.0
    return vec


def _ensure_project(db: Database, project_id: str, name: str = "Test Project") -> None:
    """Helper to ensure project exists in projects collection."""
    now = datetime.now(timezone.utc)
    db.projects.update_one(
        {"project_id": project_id},
        {"$set": {"name": name, "updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


def test_atlas_vector_index_status_reporting(test_db: Database):
    """Verify that get_atlas_vector_index_status reports accurate metadata without errors."""
    status_resp = get_atlas_vector_index_status(test_db)
    assert status_resp.index_name == "idx_incidents_vector"
    assert status_resp.target_dimension == 1024
    assert status_resp.vector_field == "embedding"
    assert status_resp.fallback_available is True
    assert status_resp.status in ("READY", "PENDING", "DOES_NOT_EXIST", "UNAVAILABLE")


def test_production_vector_adapter_project_search_and_fallback(test_db: Database):
    """Test project-scoped vector retrieval with in-memory cosine ranking."""
    adapter = ProductionMongoVectorSearchAdapter(db=test_db)
    proj_id = "proj_test_vec_scoped"
    _ensure_project(test_db, proj_id)
    dim = 1024

    vec_match = _make_unit_vector(dim, 42)
    vec_orthogonal = _make_unit_vector(dim, 99)

    inc_id_1 = f"inc_test_v1_{int(datetime.now().timestamp())}"
    inc_id_2 = f"inc_test_v2_{int(datetime.now().timestamp())}"

    test_db.incidents.insert_many([
        {
            "incident_id": inc_id_1,
            "project_id": proj_id,
            "error_type": "KeyError",
            "error_message": "KeyError: 'user_token'",
            "error_signature": compute_error_signature("KeyError", "KeyError: 'user_token'"),
            "command": "python app.py",
            "embedding": vec_match,
            "embedding_model": "voyage-code-4",
            "embedding_dimension": dim,
            "verification_status": "verified",
            "resolution_summary": "Set USER_TOKEN environment variable in secret store",
            "is_public": False,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "incident_id": inc_id_2,
            "project_id": proj_id,
            "error_type": "SyntaxError",
            "error_message": "SyntaxError: invalid syntax",
            "error_signature": compute_error_signature("SyntaxError", "SyntaxError: invalid syntax"),
            "command": "python script.py",
            "embedding": vec_orthogonal,
            "embedding_model": "voyage-code-4",
            "embedding_dimension": dim,
            "verification_status": "unverified",
            "is_public": False,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    try:
        # Search using vec_match as query vector
        results = adapter.search_project_vectors(
            query_vector=vec_match,
            project_id=proj_id,
            limit=5,
            min_score=0.50,
        )

        assert len(results) >= 1
        top = results[0]
        assert top.incident_id == inc_id_1
        assert top.project_id == proj_id
        assert top.similarity_score >= 0.95
        assert top.verification_status == FixVerificationStatus.VERIFIED
        assert top.resolution_summary == "Set USER_TOKEN environment variable in secret store"
    finally:
        test_db.incidents.delete_many({"incident_id": {"$in": [inc_id_1, inc_id_2]}})
        test_db.projects.delete_one({"project_id": proj_id})


def test_production_vector_adapter_strict_tenant_isolation(test_db: Database):
    """Verify that private incidents from project A are never returned when querying project B."""
    adapter = ProductionMongoVectorSearchAdapter(db=test_db)
    proj_a = "proj_test_tenant_a"
    proj_b = "proj_test_tenant_b"
    _ensure_project(test_db, proj_a)
    _ensure_project(test_db, proj_b)
    dim = 1024

    vec = _make_unit_vector(dim, 7)
    inc_a = f"inc_private_a_{int(datetime.now().timestamp())}"

    test_db.incidents.insert_one({
        "incident_id": inc_a,
        "project_id": proj_a,
        "error_type": "PermissionError",
        "error_message": "Access denied to proprietary ledger",
        "error_signature": compute_error_signature("PermissionError", "Access denied to proprietary ledger"),
        "command": "ledger_tool --sync",
        "embedding": vec,
        "embedding_model": "voyage-code-4",
        "embedding_dimension": dim,
        "verification_status": "verified",
        "resolution_summary": "Private resolution text",
        "is_public": False,
        "created_at": datetime.now(timezone.utc),
    })

    try:
        # 1. Project-scoped search on Proj B must return nothing
        proj_b_results = adapter.search_project_vectors(
            query_vector=vec,
            project_id=proj_b,
            limit=10,
            min_score=0.10,
        )
        assert not any(r.incident_id == inc_a for r in proj_b_results)

        # 2. Cross-project search from Proj B must NOT return private incidents from Proj A
        cross_results = adapter.search_cross_project_vectors(
            query_vector=vec,
            requesting_project_id=proj_b,
            limit=10,
            min_score=0.10,
        )
        assert not any(r.incident_id == inc_a for r in cross_results)
    finally:
        test_db.incidents.delete_one({"incident_id": inc_a})
        test_db.projects.delete_many({"project_id": {"$in": [proj_a, proj_b]}})


def test_production_vector_adapter_public_cross_project_precedents(test_db: Database):
    """Verify that public incidents can be shared across projects with disclose_project_id policy."""
    adapter = ProductionMongoVectorSearchAdapter(db=test_db)
    proj_donor = "proj_test_donor"
    proj_caller = "proj_test_caller"
    _ensure_project(test_db, proj_donor)
    _ensure_project(test_db, proj_caller)
    dim = 1024

    vec = _make_unit_vector(dim, 88)
    inc_pub_1 = f"inc_pub_anonymized_{int(datetime.now().timestamp())}"
    inc_pub_2 = f"inc_pub_disclosed_{int(datetime.now().timestamp())}"

    test_db.incidents.insert_many([
        {
            "incident_id": inc_pub_1,
            "project_id": proj_donor,
            "error_type": "ConnectionRefusedError",
            "error_message": "Failed to connect to redis on localhost:6379",
            "error_signature": compute_error_signature("ConnectionRefusedError", "Failed to connect to redis on localhost:6379"),
            "embedding": vec,
            "embedding_model": "voyage-code-4",
            "embedding_dimension": dim,
            "verification_status": "verified",
            "resolution_summary": "Start redis-server daemon",
            "is_public": True,
            "disclose_project_id": False,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "incident_id": inc_pub_2,
            "project_id": proj_donor,
            "error_type": "ConnectionRefusedError",
            "error_message": "Failed to connect to postgresql on localhost:5432",
            "error_signature": compute_error_signature("ConnectionRefusedError", "Failed to connect to postgresql on localhost:5432"),
            "embedding": vec,
            "embedding_model": "voyage-code-4",
            "embedding_dimension": dim,
            "verification_status": "verified",
            "resolution_summary": "Start postgres service",
            "is_public": True,
            "disclose_project_id": True,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    try:
        cross_matches = adapter.search_cross_project_vectors(
            query_vector=vec,
            requesting_project_id=proj_caller,
            limit=10,
            min_score=0.50,
        )

        match_ids = {m.incident_id: m for m in cross_matches}
        assert inc_pub_1 in match_ids
        assert inc_pub_2 in match_ids

        # Anonymized public incident should not disclose project_id
        assert match_ids[inc_pub_1].project_id is None
        # Disclosed public incident should disclose project_id
        assert match_ids[inc_pub_2].project_id == proj_donor
    finally:
        test_db.incidents.delete_many({"incident_id": {"$in": [inc_pub_1, inc_pub_2]}})
        test_db.projects.delete_many({"project_id": {"$in": [proj_donor, proj_caller]}})


def test_unverified_and_failed_fix_never_leaks_resolution_summary(test_db: Database):
    """Strict Unverified Fix Guarantee: unverified/failed fixes must never leak resolution summaries."""
    adapter = ProductionMongoVectorSearchAdapter(db=test_db)
    proj_id = "proj_test_fix_guarantee"
    _ensure_project(test_db, proj_id)
    dim = 1024

    vec = _make_unit_vector(dim, 15)
    inc_unverified = f"inc_unverified_{int(datetime.now().timestamp())}"
    inc_failed = f"inc_failed_{int(datetime.now().timestamp())}"

    test_db.incidents.insert_many([
        {
            "incident_id": inc_unverified,
            "project_id": proj_id,
            "error_type": "ZeroDivisionError",
            "error_message": "division by zero",
            "error_signature": compute_error_signature("ZeroDivisionError", "division by zero"),
            "embedding": vec,
            "embedding_model": "voyage-code-4",
            "embedding_dimension": dim,
            "verification_status": "unverified",
            "resolution_summary": "Unverified fix attempt that should never leak",
            "is_public": False,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "incident_id": inc_failed,
            "project_id": proj_id,
            "error_type": "ZeroDivisionError",
            "error_message": "division by zero in worker",
            "error_signature": compute_error_signature("ZeroDivisionError", "division by zero in worker"),
            "embedding": vec,
            "embedding_model": "voyage-code-4",
            "embedding_dimension": dim,
            "verification_status": "failed",
            "resolution_summary": "Failed fix attempt that broke the build",
            "is_public": False,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    try:
        results = adapter.search_project_vectors(
            query_vector=vec,
            project_id=proj_id,
            limit=5,
            min_score=0.50,
        )

        for match in results:
            assert match.resolution_summary is None, (
                f"Incident {match.incident_id} leaked resolution_summary with status {match.verification_status}"
            )
    finally:
        test_db.incidents.delete_many({"incident_id": {"$in": [inc_unverified, inc_failed]}})
        test_db.projects.delete_one({"project_id": proj_id})


def test_empty_and_corrupt_vector_handling(test_db: Database):
    """Verify that malformed or non-finite query vectors return empty lists safely."""
    adapter = ProductionMongoVectorSearchAdapter(db=test_db)

    # Empty list
    assert adapter.search_project_vectors([], "proj_test") == []
    # All zeros
    assert adapter.search_project_vectors([0.0] * 1024, "proj_test") == []
    # Non-finite elements
    assert adapter.search_project_vectors([float("inf")] * 1024, "proj_test") == []
    assert adapter.search_project_vectors([float("nan")] * 1024, "proj_test") == []
    # None or non-list
    assert adapter.search_project_vectors(None, "proj_test") == []  # type: ignore


def test_vector_search_endpoints_via_testclient(client: TestClient):
    """Verify that vector search status and search endpoints respond properly via HTTP."""
    # 1. GET /api/v1/incidents/vector-search/status
    res = client.get("/api/v1/incidents/vector-search/status")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "status" in body["data"]
    assert "queryable" in body["data"]
    assert body["data"]["target_dimension"] == 1024

    # 2. POST /api/v1/incidents/search/vector on empty project
    res_search = client.post(
        "/api/v1/incidents/search/vector",
        params={
            "query_text": "TypeError: unsupported operand type for +",
            "project_id": "proj_nonexistent_test",
            "limit": 5,
            "min_score": 0.50,
        },
    )
    assert res_search.status_code == 200
    search_body = res_search.json()
    assert search_body["success"] is True
    assert isinstance(search_body["data"], list)


def test_ai_diagnosis_retrieval_incorporates_vector_candidates(test_db: Database):
    """End-to-end integration: AI diagnosis uses ProductionMongoVectorSearchAdapter safely."""
    proj_id = "proj_test_ai_diag_vector"
    inc_target = f"inc_target_{int(datetime.now().timestamp())}"
    inc_precedent = f"inc_prec_{int(datetime.now().timestamp())}"
    dim = 1024

    vec = _make_unit_vector(dim, 33)

    # Register project
    _ensure_project(test_db, proj_id, "Test Vector Project")

    # Insert precedent with verified fix and embedding
    test_db.incidents.insert_one({
        "incident_id": inc_precedent,
        "project_id": proj_id,
        "error_type": "FileNotFoundError",
        "error_message": "FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'",
        "error_signature": compute_error_signature("FileNotFoundError", "FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'"),
        "command": "python service.py",
        "embedding": vec,
        "embedding_model": "voyage-code-4",
        "embedding_dimension": dim,
        "verification_status": "verified",
        "resolution_summary": "Copy config.example.yaml to config.yaml before starting service",
        "is_public": False,
        "created_at": datetime.now(timezone.utc),
    })

    # Insert target incident to diagnose
    test_db.incidents.insert_one({
        "incident_id": inc_target,
        "project_id": proj_id,
        "error_type": "FileNotFoundError",
        "error_message": "FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'",
        "error_signature": compute_error_signature("FileNotFoundError", "FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'"),
        "command": "python service.py",
        "embedding": vec,
        "embedding_model": "voyage-code-4",
        "embedding_dimension": dim,
        "diagnosis_status": "pending",
        "created_at": datetime.now(timezone.utc),
    })

    try:
        # Run diagnosis orchestrator with offline inference enabled to avoid paid external LLM calls
        diag_resp, is_new = generate_and_store_incident_diagnosis(
            db=test_db,
            incident_id=inc_target,
            disable_external_inference=True,
            force_recheck=True,
        )

        assert diag_resp is not None
        assert diag_resp.summary is not None
        assert len(diag_resp.evidence) > 0
        # Target incident status should be diagnosed
        updated_inc = test_db.incidents.find_one({"incident_id": inc_target})
        assert updated_inc["diagnosis_status"] == "diagnosed"
    finally:
        test_db.incidents.delete_many({"incident_id": {"$in": [inc_target, inc_precedent]}})
        test_db.diagnoses.delete_many({"incident_id": inc_target})
        test_db.projects.delete_one({"project_id": proj_id})
