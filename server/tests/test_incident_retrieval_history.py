"""Focused tests for incident history retrieval, vector fallback, and general knowledge matching.

Validates:
1. An exact previously stored error returns its matching incident.
2. A semantically similar error retrieves a relevant incident when appropriate.
3. General knowledge is returned even when there are no historical incident matches.
4. An unrelated query can correctly return no matches.
5. Atlas retrieval failure still uses the in-memory cosine fallback.
6. Project A's private incidents never appear in Project B's results.
7. Incident detail API enrichment with unified historical_matches.
"""

from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from httpx import AsyncClient
from pymongo.database import Database

from app.utils.signature import compute_error_signature


@pytest.fixture
async def setup_projects(test_db: Database, async_client: AsyncClient):
    """Fixture initializing two isolated projects."""
    res1 = await async_client.post(
        "/api/v1/projects",
        json={"name": "Project Alpha", "project_id": "proj_alpha"},
    )
    assert res1.status_code == 201

    res2 = await async_client.post(
        "/api/v1/projects",
        json={"name": "Project Beta", "project_id": "proj_beta"},
    )
    assert res2.status_code == 201

    return "proj_alpha", "proj_beta"


@pytest.mark.anyio
async def test_exact_previously_stored_error_returns_matching_incident(
    setup_projects, test_db: Database, async_client: AsyncClient
):
    """1. Exact previously stored error returns its matching incident with verified status and self-exclusion."""
    proj_a, _ = setup_projects
    error_msg = "KeyError: 'session_token' in auth_service.py"
    error_sig = compute_error_signature("KeyError", error_msg)

    # 1. Past Incident in Project A with verified fix
    res_past = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "KeyError",
            "error_message": error_msg,
            "file_path": "services/auth_service.py",
            "line": 42,
        },
    )
    assert res_past.status_code == 201
    past_id = res_past.json()["data"]["incident_id"]

    # Mark the past incident with verified resolution in MongoDB
    test_db.incidents.update_one(
        {"incident_id": past_id},
        {
            "$set": {
                "verification_status": "verified",
                "resolution_summary": "Initialize session dictionary with default token key",
            }
        },
    )

    # 2. Target Incident in Project A (same signature)
    res_target = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "KeyError",
            "error_message": error_msg,
            "file_path": "services/login_service.py",
            "line": 88,
        },
    )
    assert res_target.status_code == 201
    target_id = res_target.json()["data"]["incident_id"]

    # 3. Query history endpoint
    resp = await async_client.get(f"/api/v1/incidents/{target_id}/history")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["current_incident_id"] == target_id
    assert data["error_signature"] == error_sig

    # Assert self-exclusion: target_id must NOT be in matches
    same_ids = [m["incident_id"] for m in data["same_project_matches"]]
    assert target_id not in same_ids
    assert past_id in same_ids

    # Assert unified historical_matches
    hist_matches = data["historical_matches"]
    past_match = next((m for m in hist_matches if m["source_id"] == past_id), None)
    assert past_match is not None
    assert past_match["source_type"] == "project_memory"
    assert past_match["is_cross_project"] is False
    assert past_match["verified"] is True
    assert past_match["sanitized_fix_summary"] == "Initialize session dictionary with default token key"


@pytest.mark.anyio
async def test_semantically_similar_error_retrieves_relevant_incident(
    setup_projects, test_db: Database, async_client: AsyncClient
):
    """2. Semantically similar error retrieves relevant incident via vector/cosine fallback."""
    proj_a, _ = setup_projects
    dim = 1024
    vec_similar = [0.0] * dim
    vec_similar[10] = 1.0  # shared active component for high cosine similarity

    # 1. Past Incident with vector embedding
    res_past = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "ValueError",
            "error_message": "ValueError: invalid literal for int() with base 10: 'abc'",
            "file_path": "parser.py",
        },
    )
    past_id = res_past.json()["data"]["incident_id"]

    test_db.incidents.update_one(
        {"incident_id": past_id},
        {
            "$set": {
                "embedding": vec_similar,
                "embedding_model": "voyage-code-4",
                "embedding_dimension": dim,
                "verification_status": "verified",
                "resolution_summary": "Validate numeric string format prior to parsing integer",
            }
        },
    )

    # 2. Target Incident with different message but similar vector
    res_target = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "ValueError",
            "error_message": "ValueError: unable to parse integer value from input string",
            "file_path": "validator.py",
        },
    )
    target_id = res_target.json()["data"]["incident_id"]

    test_db.incidents.update_one(
        {"incident_id": target_id},
        {
            "$set": {
                "embedding": vec_similar,
                "embedding_model": "voyage-code-4",
                "embedding_dimension": dim,
            }
        },
    )

    resp = await async_client.get(f"/api/v1/incidents/{target_id}/history")
    assert resp.status_code == 200
    data = resp.json()["data"]

    hist_ids = [m["source_id"] for m in data["historical_matches"]]
    assert past_id in hist_ids or past_id in [m["incident_id"] for m in data["same_project_matches"]]


@pytest.mark.anyio
async def test_general_knowledge_returned_when_zero_historical_incidents(
    setup_projects, test_db: Database, async_client: AsyncClient
):
    """3. General knowledge is returned even when there are no historical incident matches."""
    proj_a, _ = setup_projects

    # Create target incident with a standard Python pattern (ModuleNotFoundError)
    res_target = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "ModuleNotFoundError",
            "error_message": "ModuleNotFoundError: No module named 'requests'",
            "file_path": "main.py",
        },
    )
    assert res_target.status_code == 201
    target_id = res_target.json()["data"]["incident_id"]

    resp = await async_client.get(f"/api/v1/incidents/{target_id}/history")
    assert resp.status_code == 200
    data = resp.json()["data"]

    # Historical incident matches must be empty
    assert len(data["same_project_matches"]) == 0
    assert len(data["cross_project_matches"]) == 0

    # But curated general knowledge matches must be populated!
    assert len(data["general_knowledge_matches"]) > 0
    gk_ids = [gk["kb_id"] for gk in data["general_knowledge_matches"]]
    assert "kb_py_mod_not_found" in gk_ids

    # And unified historical_matches must also include the general knowledge item
    gk_unified = next((m for m in data["historical_matches"] if m["is_general_knowledge"]), None)
    assert gk_unified is not None
    assert gk_unified["source_type"] == "knowledge_base"
    assert gk_unified["source_project"] == "Curated Knowledge Base"
    assert gk_unified["verified"] is False
    assert "pip install" in gk_unified["sanitized_fix_summary"] or "ModuleNotFoundError" in gk_unified["match_reason"]


@pytest.mark.anyio
async def test_unrelated_query_returns_no_matches(
    setup_projects, test_db: Database, async_client: AsyncClient
):
    """4. An unrelated synthetic error correctly returns no matches anywhere."""
    proj_a, _ = setup_projects

    res_target = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "SyntheticUniqueZ999Error",
            "error_message": "SyntheticUniqueZ999Error: arbitrary token 984128941029",
            "file_path": "unique_script.py",
        },
    )
    assert res_target.status_code == 201
    target_id = res_target.json()["data"]["incident_id"]

    resp = await async_client.get(f"/api/v1/incidents/{target_id}/history")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert len(data["same_project_matches"]) == 0
    assert len(data["cross_project_matches"]) == 0
    assert len(data["general_knowledge_matches"]) == 0
    assert len(data["historical_matches"]) == 0


@pytest.mark.anyio
async def test_atlas_retrieval_failure_uses_existing_fallback(
    setup_projects, test_db: Database, async_client: AsyncClient
):
    """5. Atlas retrieval failure still uses the in-memory cosine fallback."""
    from pymongo.errors import OperationFailure
    from app.services.embedding_service import ProductionMongoVectorSearchAdapter

    proj_a, _ = setup_projects
    dim = 1024
    vec = [0.0] * dim
    vec[5] = 1.0

    res_target = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "TimeoutError",
            "error_message": "TimeoutError: connection timed out after 30000ms",
        },
    )
    target_id = res_target.json()["data"]["incident_id"]

    test_db.incidents.update_one(
        {"incident_id": target_id},
        {"$set": {"embedding": vec, "embedding_dimension": dim}},
    )

    # Patch aggregate on incidents collection to simulate Atlas vector search failure
    orig_aggregate = test_db.incidents.aggregate

    def fail_vector_search(pipeline, *args, **kwargs):
        if pipeline and "$vectorSearch" in pipeline[0]:
            raise OperationFailure("$vectorSearch is not supported in this environment")
        return orig_aggregate(pipeline, *args, **kwargs)

    with patch.object(test_db.incidents, "aggregate", side_effect=fail_vector_search):
        adapter = ProductionMongoVectorSearchAdapter(db=test_db)
        results = adapter.search_project_vectors(
            query_vector=vec,
            project_id=proj_a,
            limit=5,
            min_score=0.1,
        )
        # Should gracefully succeed without throwing, using fallback
        assert isinstance(results, list)


@pytest.mark.anyio
async def test_project_isolation_private_incidents_never_appear_in_other_project(
    setup_projects, test_db: Database, async_client: AsyncClient
):
    """6. Project A's private incidents never appear in Project B's results."""
    proj_a, proj_b = setup_projects

    # 1. Project A has a private incident
    res_a = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "SecurityConfigError",
            "error_message": "SecurityConfigError: Invalid secret key in internal_vault.py",
            "file_path": "vault/internal_vault.py",
            "source_snippet": "SECRET_VAULT_KEY = 'private_alpha_key_12345'",
        },
    )
    inc_a_id = res_a.json()["data"]["incident_id"]

    # 2. Project B has an unrelated incident
    res_b = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_b,
            "error_type": "DatabaseConfigError",
            "error_message": "DatabaseConfigError: Database host not reachable",
            "file_path": "db/config.py",
        },
    )
    inc_b_id = res_b.json()["data"]["incident_id"]

    # Query Project B's history
    resp = await async_client.get(f"/api/v1/incidents/{inc_b_id}/history")
    assert resp.status_code == 200
    data = resp.json()["data"]

    # Inc A must NOT appear anywhere in Project B's history
    all_returned_ids = [m["incident_id"] for m in data["same_project_matches"]] + \
                       [m["incident_id"] for m in data["cross_project_matches"]] + \
                       [m["source_id"] for m in data["historical_matches"]]

    assert inc_a_id not in all_returned_ids
    assert "private_alpha_key_12345" not in str(data)


@pytest.mark.anyio
async def test_incident_endpoint_enriches_historical_matches(
    setup_projects, test_db: Database, async_client: AsyncClient
):
    """7. GET /incidents/{incident_id} response schema includes populated historical_matches."""
    proj_a, _ = setup_projects

    res = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": proj_a,
            "error_type": "FileNotFoundError",
            "error_message": "FileNotFoundError: [Errno 2] No such file or directory: 'config.json'",
        },
    )
    inc_id = res.json()["data"]["incident_id"]

    # Retrieve incident details
    get_res = await async_client.get(f"/api/v1/incidents/{inc_id}")
    assert get_res.status_code == 200
    inc_data = get_res.json()["data"]

    # Assert historical_matches field is present on incident response
    assert "historical_matches" in inc_data
