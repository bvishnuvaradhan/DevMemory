"""Service layer for AI diagnosis persistence, retrieval, and history."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from fastapi import HTTPException, status
from pymongo import DESCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.schemas.diagnosis import DiagnosisCreate, DiagnosisResponse
from app.schemas.pagination import PaginatedResponse


def create_diagnosis(
    db: Database,
    incident_id: str,
    payload: DiagnosisCreate,
    lease_token: Optional[str] = None,
) -> tuple[DiagnosisResponse, bool]:
    """Store a structured AI diagnosis linked to an existing incident.

    Args:
        db: MongoDB database handle.
        incident_id: Incident identifier.
        payload: Diagnosis creation schema.
        lease_token: Optional active lease token for ownership-verified status update.

    Returns:
        (DiagnosisResponse, is_new: bool)
    """
    # 1. Validate that the referenced incident exists
    incident = db.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    # 2. Derive project_id from the verified incident record
    project_id = incident["project_id"]
    diagnosis_id = payload.diagnosis_id or f"diag_{uuid4().hex[:12]}"

    # 3. Idempotent check for client-supplied diagnosis_id
    if payload.diagnosis_id:
        existing = db.diagnoses.find_one({"diagnosis_id": payload.diagnosis_id}, {"_id": 0})
        if existing:
            resp = DiagnosisResponse(**existing)
            resp.idempotent = True
            return resp, False

    now = datetime.now(timezone.utc)
    doc = {
        "diagnosis_id": diagnosis_id,
        "incident_id": incident_id,
        "project_id": project_id,
        "summary": payload.summary,
        "hypotheses": [h.model_dump() for h in payload.hypotheses],
        "suggested_fix": payload.suggested_fix,
        "matched_memory": [m.model_dump() for m in payload.matched_memory],
        "evidence": payload.evidence,
        "confidence": payload.confidence,
        "source": payload.source,
        "created_at": now,
    }

    try:
        db.diagnoses.insert_one(doc)
    except DuplicateKeyError:
        existing = db.diagnoses.find_one({"diagnosis_id": diagnosis_id}, {"_id": 0})
        if existing:
            resp = DiagnosisResponse(**existing)
            resp.idempotent = True
            return resp, False
        raise

    # 4. Update incident diagnosis status with ownership protection
    update_filter: dict = {"incident_id": incident_id}
    if lease_token:
        update_filter["diagnosis_lease_token"] = lease_token

    db.incidents.update_one(
        update_filter,
        {
            "$set": {"diagnosis_status": "diagnosed"},
            "$unset": {
                "diagnosis_lease_token": "",
                "diagnosis_lease_expires_at": "",
            },
        },
    )

    resp = DiagnosisResponse(**doc)
    resp.idempotent = False
    return resp, True


def get_latest_diagnosis(
    db: Database,
    incident_id: str,
) -> Optional[DiagnosisResponse]:
    """Retrieve the most recent diagnosis for an incident with automatic self-healing status reconciliation."""
    incident = db.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    doc = db.diagnoses.find_one(
        {"incident_id": incident_id},
        {"_id": 0},
        sort=[("created_at", DESCENDING)],
    )
    if not doc:
        return None

    # Self-healing reconciliation: if a diagnosis exists but incident status is not 'diagnosed',
    # reconcile incident diagnosis_status to 'diagnosed'
    if incident.get("diagnosis_status") != "diagnosed":
        db.incidents.update_one(
            {"incident_id": incident_id},
            {
                "$set": {"diagnosis_status": "diagnosed"},
                "$unset": {"diagnosis_lease_token": "", "diagnosis_lease_expires_at": ""},
            },
        )

    return DiagnosisResponse(**doc)


def list_incident_diagnoses(
    db: Database,
    incident_id: str,
    limit: int = 50,
    skip: int = 0,
) -> PaginatedResponse[DiagnosisResponse]:
    """Retrieve paginated diagnosis history for an incident sorted newest first."""
    incident = db.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    filter_query = {"incident_id": incident_id}
    total = db.diagnoses.count_documents(filter_query)
    cursor = (
        db.diagnoses.find(filter_query, {"_id": 0})
        .sort("created_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    items = [DiagnosisResponse(**d) for d in cursor]

    return PaginatedResponse[DiagnosisResponse](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )
