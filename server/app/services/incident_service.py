"""Service layer for incident creation, deduplication, and retrieval."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from fastapi import HTTPException, status
from pymongo import DESCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.schemas.incident import IncidentCreate, IncidentResponse
from app.schemas.pagination import PaginatedResponse
from app.utils.signature import compute_error_signature


def create_or_get_incident(
    db: Database,
    project_id: str,
    event_id: Optional[str],
    error_type: str,
    error_message: str,
    file_path: Optional[str] = None,
    line: Optional[int] = None,
    column: Optional[int] = None,
    source_snippet: Optional[str] = None,
) -> IncidentResponse:
    """Create an incident or return existing record for the same event idempotently."""
    signature = compute_error_signature(error_type, error_message)
    incident_id = f"inc_{event_id}" if event_id else f"inc_{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    doc = {
        "incident_id": incident_id,
        "event_id": event_id,
        "project_id": project_id,
        "error_type": error_type,
        "error_message": error_message,
        "error_signature": signature,
        "file_path": file_path,
        "line": line,
        "column": column,
        "source_snippet": source_snippet,
        "diagnosis_status": "pending",
        "created_at": now,
    }

    # Automatically compute and attach embedding vector if possible (fault-tolerant)
    try:
        import os
        from app.config import get_settings
        from app.services.embedding_service import generate_incident_embedding, resolve_target_dimension

        settings = get_settings()
        v_field = os.getenv("MONGODB_VECTOR_FIELD") or settings.MONGODB_VECTOR_FIELD or "embedding"
        target_dim = resolve_target_dimension()
        emb_res = generate_incident_embedding(
            error_message=error_message,
            stack_trace=source_snippet,
            command=None,
            expected_dimension=target_dim,
        )
        status_str = (
            emb_res.status.value
            if hasattr(emb_res.status, "value")
            else str(emb_res.status)
        )
        doc[v_field] = emb_res.vector
        doc["embedding_model"] = emb_res.model
        doc["embedding_dimension"] = emb_res.dimension
        doc["embedding_status"] = status_str
        doc["embedding_is_fallback"] = bool(emb_res.is_fallback)
        doc["embedded_at"] = now
    except Exception:
        # Fault isolation: embedding generation failure must not prevent incident creation
        pass

    try:
        db.incidents.insert_one(doc)
    except DuplicateKeyError:
        # Fetch existing incident matching event_id or incident_id
        query = {"project_id": project_id, "event_id": event_id} if event_id else {"incident_id": incident_id}
        existing = db.incidents.find_one(query, {"_id": 0})
        if existing:
            return IncidentResponse(**existing)
        # If still not found by query, attempt direct incident_id lookup
        existing_by_id = db.incidents.find_one({"incident_id": incident_id}, {"_id": 0})
        if existing_by_id:
            return IncidentResponse(**existing_by_id)
        raise

    return IncidentResponse(**doc)


def create_incident_direct(db: Database, payload: IncidentCreate) -> IncidentResponse:
    """Explicitly create an incident via API."""
    # Verify project exists
    project = db.projects.find_one({"project_id": payload.project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{payload.project_id}' not found.",
        )

    return create_or_get_incident(
        db=db,
        project_id=payload.project_id,
        event_id=payload.event_id,
        error_type=payload.error_type,
        error_message=payload.error_message,
        file_path=payload.file_path,
        line=payload.line,
        column=payload.column,
        source_snippet=payload.source_snippet,
    )


def _enrich_incidents_with_diagnoses(db: Database, docs: list[dict]) -> list[dict]:
    """Batch-enrich incident documents with their latest diagnosis records from db.diagnoses."""
    if not docs:
        return docs
    incident_ids = [d["incident_id"] for d in docs if "incident_id" in d]
    if not incident_ids:
        return docs

    diag_cursor = db.diagnoses.find(
        {"incident_id": {"$in": incident_ids}},
        {"_id": 0},
    ).sort("created_at", DESCENDING)

    diag_map: dict[str, dict] = {}
    for diag in diag_cursor:
        iid = diag.get("incident_id")
        if iid and iid not in diag_map:  # Keep newest since sorted DESCENDING
            diag_map[iid] = diag

    for d in docs:
        iid = d.get("incident_id")
        if iid and iid in diag_map:
            d["ai_diagnosis"] = diag_map[iid]
            if d.get("diagnosis_status") == "pending":
                d["diagnosis_status"] = "diagnosed"

    return docs


def get_incident(db: Database, incident_id: str) -> Optional[IncidentResponse]:
    """Retrieve an incident by its unique ID enriched with its latest diagnosis."""
    doc = db.incidents.find_one({"incident_id": incident_id}, {"_id": 0})
    if not doc:
        return None

    # Attach latest diagnosis if present in db.diagnoses
    diag = db.diagnoses.find_one(
        {"incident_id": incident_id},
        {"_id": 0},
        sort=[("created_at", DESCENDING)],
    )
    if diag:
        doc["ai_diagnosis"] = diag
        if doc.get("diagnosis_status") == "pending":
            doc["diagnosis_status"] = "diagnosed"

    return IncidentResponse(**doc)


def list_project_incidents(
    db: Database,
    project_id: str,
    limit: int = 50,
    skip: int = 0,
) -> PaginatedResponse[IncidentResponse]:
    """Retrieve paginated incidents for a specific project sorted newest first."""
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    filter_query = {"project_id": project_id}
    total = db.incidents.count_documents(filter_query)
    cursor = db.incidents.find(filter_query, {"_id": 0}).sort("created_at", DESCENDING).skip(skip).limit(limit)
    docs = list(cursor)
    _enrich_incidents_with_diagnoses(db, docs)
    items = [IncidentResponse(**d) for d in docs]

    return PaginatedResponse[IncidentResponse](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )


def list_incidents(
    db: Database,
    project_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
) -> PaginatedResponse[IncidentResponse]:
    """Retrieve paginated incidents across all projects or filtered by project ID."""
    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    filter_query: dict = {}
    if project_id:
        filter_query["project_id"] = project_id

    total = db.incidents.count_documents(filter_query)
    cursor = db.incidents.find(filter_query, {"_id": 0}).sort("created_at", DESCENDING).skip(skip).limit(limit)
    docs = list(cursor)
    _enrich_incidents_with_diagnoses(db, docs)
    items = [IncidentResponse(**d) for d in docs]

    return PaginatedResponse[IncidentResponse](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )
