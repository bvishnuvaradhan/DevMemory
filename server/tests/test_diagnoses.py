"""Tests for AI diagnosis persistence, retrieval, and idempotency."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def sample_incident(test_db, async_client: AsyncClient):
    """Fixture providing an existing project and incident."""
    await async_client.post(
        "/api/v1/projects",
        json={"name": "DiagnosisApp", "project_id": "proj_diag"},
    )
    res = await async_client.post(
        "/api/v1/incidents",
        json={
            "project_id": "proj_diag",
            "error_type": "ZeroDivisionError",
            "error_message": "division by zero",
            "file_path": "calculator.py",
            "line": 10,
        },
    )
    return res.json()["data"]["incident_id"]


@pytest.mark.anyio
async def test_create_diagnosis_success(sample_incident, async_client: AsyncClient):
    """Scenario 1: Create a structured diagnosis for an existing incident."""
    payload = {
        "summary": "Attempted to divide integer by zero in calculate_ratio()",
        "hypotheses": [
            {
                "cause": "Denominator variable total_count was 0 due to empty queryset",
                "is_observed": True,
                "details": "Observed total_count = 0 in local scope before line 10",
            },
            {
                "cause": "Upstream data ingestion pipeline failed to populate records",
                "is_observed": False,
                "details": "Speculative hypothesis requiring upstream pipeline inspection",
            },
        ],
        "suggested_fix": "Add guard check: if total_count == 0: return 0.0",
        "matched_memory": [
            {
                "source_id": "kb_python_zerodiv",
                "source_type": "knowledge_base",
                "relevance_reason": "Standard Python division by zero guard pattern",
            }
        ],
        "evidence": ["ZeroDivisionError raised at calculator.py:10"],
        "confidence": 0.95,
        "source": "groq/llama-3.3-70b-versatile",
    }
    response = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/diagnosis",
        json=payload,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["incident_id"] == sample_incident
    assert data["project_id"] == "proj_diag"
    assert data["summary"] == payload["summary"]
    assert len(data["hypotheses"]) == 2
    assert data["hypotheses"][0]["is_observed"] is True
    assert data["confidence"] == 0.95
    assert data["idempotent"] is False


@pytest.mark.anyio
async def test_create_diagnosis_missing_incident(async_client: AsyncClient):
    """Scenario 2: Reject diagnosis creation for a missing incident (HTTP 404)."""
    response = await async_client.post(
        "/api/v1/incidents/inc_non_existent/diagnosis",
        json={"summary": "Sample summary"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert "not found" in body["error"].lower()


@pytest.mark.anyio
async def test_create_diagnosis_invalid_payload(sample_incident, async_client: AsyncClient):
    """Scenario 3: Reject invalid diagnosis payload (HTTP 422)."""
    response = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/diagnosis",
        json={"confidence": 2.5},  # Missing summary, confidence > 1.0
    )
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "Validation failed" in body["error"]


@pytest.mark.anyio
async def test_get_latest_diagnosis(sample_incident, async_client: AsyncClient):
    """Scenario 4: Retrieve the latest diagnosis for an incident."""
    # Post first diagnosis
    await async_client.post(
        f"/api/v1/incidents/{sample_incident}/diagnosis",
        json={"summary": "First initial hypothesis"},
    )
    # Post updated second diagnosis
    await async_client.post(
        f"/api/v1/incidents/{sample_incident}/diagnosis",
        json={"summary": "Refined second analysis with confirmed root cause"},
    )

    response = await async_client.get(f"/api/v1/incidents/{sample_incident}/diagnosis")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["summary"] == "Refined second analysis with confirmed root cause"


@pytest.mark.anyio
async def test_list_incident_diagnoses_history(sample_incident, async_client: AsyncClient):
    """Scenario 5 & 6: Preserve multiple diagnosis records and retrieve paginated history."""
    for i in range(3):
        await async_client.post(
            f"/api/v1/incidents/{sample_incident}/diagnosis",
            json={"summary": f"Diagnosis iteration {i}"},
        )

    response = await async_client.get(
        f"/api/v1/incidents/{sample_incident}/diagnoses?limit=2&skip=0"
    )
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["items"][0]["summary"] == "Diagnosis iteration 2"


@pytest.mark.anyio
async def test_diagnosis_idempotency_retry(sample_incident, test_db, async_client: AsyncClient):
    """Scenario 7: Repeated submissions with same diagnosis_id return existing record without duplication."""
    payload = {
        "diagnosis_id": "diag_stable_001",
        "summary": "Root cause identified as missing environment variable",
    }

    res1 = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/diagnosis",
        json=payload,
    )
    assert res1.status_code == 201
    assert res1.json()["data"]["idempotent"] is False

    res2 = await async_client.post(
        f"/api/v1/incidents/{sample_incident}/diagnosis",
        json=payload,
    )
    assert res2.status_code == 200
    assert res2.json()["data"]["idempotent"] is True

    # Database count remains strictly 1
    assert test_db.diagnoses.count_documents({"diagnosis_id": "diag_stable_001"}) == 1
