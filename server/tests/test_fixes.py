"""Tests for fix proposals, lifecycle transitions, and strict verification evidence rules."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def sample_incident(test_db, async_client: AsyncClient):
    """Fixture providing an existing project and incident."""
    await async_client.post(
        "/api/v1/projects",
        json={"name": "FixApp", "project_id": "proj_fix"},
    )
    res = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": "proj_fix",
            "error_type": "TypeError",
            "error_message": "Cannot read properties of undefined (reading 'map')",
        },
    )
    return res.json()["data"]["incident_id"]


@pytest.mark.anyio
async def test_create_proposed_fix_success(sample_incident, async_client: AsyncClient):
    """Scenario 8 & 10: Create a proposed fix with initial 'proposed' status and derived project_id."""
    payload = {
        "description": "Add optional chaining: items?.map(i => i.name)",
    }
    response = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/fixes",
        json=payload,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["incident_id"] == sample_incident
    assert data["project_id"] == "proj_fix"
    assert data["status"] == "proposed"
    assert data["verified_at"] is None
    assert data["fix_id"].startswith("fix_")


@pytest.mark.anyio
async def test_create_fix_missing_incident(async_client: AsyncClient):
    """Scenario 9: Reject fix creation for non-existent incident (HTTP 404)."""
    response = await async_client.post(
        "/api/v1/incidents/inc_unknown/fixes",
        json={"description": "Some code fix"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert "not found" in body["error"].lower()


@pytest.mark.anyio
async def test_valid_status_transitions_lifecycle(sample_incident, async_client: AsyncClient):
    """Scenario 11: Proposed -> Applied -> Verifying -> Verified with command evidence."""
    # 1. Create proposed fix
    create_res = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/fixes",
        json={"description": "Wrap in try-except block"},
    )
    fix_id = create_res.json()["data"]["fix_id"]

    # 2. Transition proposed -> applied
    patch1 = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={"status": "applied"},
    )
    assert patch1.status_code == 200
    assert patch1.json()["data"]["status"] == "applied"

    # 3. Transition applied -> verifying
    patch2 = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={"status": "verifying"},
    )
    assert patch2.status_code == 200
    assert patch2.json()["data"]["status"] == "verifying"

    # 4. Transition verifying -> verified (with valid execution evidence)
    patch3 = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={
            "status": "verified",
            "verification_method": "command",
            "verification_command": "pytest tests/test_calc.py",
            "verification_exit_code": 0,
            "verification_source": "test_runner",
            "verification_details": "1 passed in 0.05s",
        },
    )
    assert patch3.status_code == 200
    verified_data = patch3.json()["data"]
    assert verified_data["status"] == "verified"
    assert verified_data["verified_at"] is not None
    assert verified_data["verification_exit_code"] == 0


@pytest.mark.anyio
async def test_invalid_status_transition_conflict(sample_incident, async_client: AsyncClient):
    """Scenario 12: Invalid transition rejected with HTTP 409 Conflict."""
    create_res = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/fixes",
        json={"description": "Sample fix"},
    )
    fix_id = create_res.json()["data"]["fix_id"]

    # Try illegal jump: proposed cannot directly jump to verified without verification evidence/step
    bad_patch = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={"status": "verified"},
    )
    # Blocked by transition policy (proposed -> verified is not allowed) or evidence rule
    assert bad_patch.status_code in (409, 422)
    assert bad_patch.json()["success"] is False


@pytest.mark.anyio
async def test_reject_verification_without_evidence(sample_incident, async_client: AsyncClient):
    """Scenario 13: Attempting to mark fix as verified without test execution or user confirmation returns 422."""
    create_res = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/fixes",
        json={"description": "Fix without tests"},
    )
    fix_id = create_res.json()["data"]["fix_id"]

    # Move to verifying
    await async_client.patch(f"/api/v1/fixes/{fix_id}", json={"status": "verifying"})

    # Attempt to verify with failing exit code (1)
    fail_res = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={
            "status": "verified",
            "verification_command": "npm test",
            "verification_exit_code": 1,  # FAILED command!
        },
    )
    assert fail_res.status_code == 422
    assert "Cannot mark fix as verified without supporting verification evidence" in fail_res.json()["error"]


@pytest.mark.anyio
async def test_user_confirmation_pathway_distinction(sample_incident, async_client: AsyncClient):
    """Scenario 15: Explicit user confirmation is supported and distinctly labeled from automated tests."""
    create_res = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/fixes",
        json={"description": "Visual UI alignment fix"},
    )
    fix_id = create_res.json()["data"]["fix_id"]

    await async_client.patch(f"/api/v1/fixes/{fix_id}", json={"status": "verifying"})

    verify_res = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={
            "status": "verified",
            "verification_source": "user_confirmation",
            "verification_details": "Developer visually confirmed button alignment in browser",
        },
    )
    assert verify_res.status_code == 200
    data = verify_res.json()["data"]
    assert data["status"] == "verified"
    assert data["verification_source"] == "user_confirmation"
    assert data["verified_at"] is not None


@pytest.mark.anyio
async def test_reverted_fix_clears_verified_at(sample_incident, async_client: AsyncClient):
    """Scenario 16 & 17: Reverting a verified fix resets verified_at to None."""
    # Create and verify a fix
    res = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/fixes",
        json={"description": "Temporary hotfix"},
    )
    fix_id = res.json()["data"]["fix_id"]
    await async_client.patch(f"/api/v1/fixes/{fix_id}", json={"status": "verifying"})
    await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={
            "status": "verified",
            "verification_command": "pytest",
            "verification_exit_code": 0,
        },
    )

    # Now revert the fix
    revert_res = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={"status": "reverted", "verification_details": "Fix caused side effect, reverted."},
    )
    assert revert_res.status_code == 200
    revert_data = revert_res.json()["data"]
    assert revert_data["status"] == "reverted"
    # verified_at MUST be None after reversion!
    assert revert_data["verified_at"] is None


@pytest.mark.anyio
async def test_list_and_get_fixes(sample_incident, async_client: AsyncClient):
    """Scenario 18: Retrieve fix history for an incident and single fix by ID."""
    await async_client.post(
        f"/api/v1/incidents/{sample_incident}/fixes",
        json={"description": "Solution A"},
    )
    res_b = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/fixes",
        json={"description": "Solution B"},
    )
    fix_b_id = res_b.json()["data"]["fix_id"]

    # 1. Retrieve single fix by ID
    get_res = await async_client.get(f"/api/v1/fixes/{fix_b_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["description"] == "Solution B"

    # 2. List all fixes for incident
    list_res = await async_client.get(f"/api/v1/incidents/{sample_incident}/fixes")
    assert list_res.status_code == 200
    list_data = list_res.json()["data"]
    assert list_data["total"] == 2
    assert len(list_data["items"]) == 2


@pytest.mark.anyio
async def test_fix_malformed_update_rejected(sample_incident, async_client: AsyncClient):
    """Scenario 19: Malformed status update rejected with HTTP 422."""
    res = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/fixes",
        json={"description": "Fix candidate"},
    )
    fix_id = res.json()["data"]["fix_id"]

    bad_patch = await async_client.patch(
        f"/api/v1/fixes/{fix_id}",
        json={"status": "invalid_status_enum"},
    )
    assert bad_patch.status_code == 422
    assert bad_patch.json()["success"] is False
