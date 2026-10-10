"""Incident registration, retrieval, historical memory, diagnosis, and fix tracking API routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas.analytics import IncidentHistoryResponse
from app.schemas.diagnosis import DiagnosisCreate, DiagnosisResponse
from app.schemas.fix import FixOutcomeCreate, FixOutcomeResponse
from app.schemas.incident import (
    EmbeddingBackfillResponse,
    EmbeddingProviderStatusResponse,
    IncidentCreate,
    IncidentEmbeddingResponse,
    IncidentResponse,
    VectorSearchMatchItem,
    VectorSearchStatusResponse,
)
from app.schemas.pagination import PaginatedResponse
from app.schemas import ResponseEnvelope
from app.services import (
    ai_service,
    analytics_service,
    diagnosis_service,
    embedding_service,
    fix_service,
    incident_service,
)

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get(
    "/embedding-provider/readiness",
    response_model=ResponseEnvelope[EmbeddingProviderStatusResponse],
    summary="Check embedding provider configuration and readiness safely",
)
async def get_embedding_provider_readiness_endpoint():
    status_resp = embedding_service.check_embedding_provider_readiness()
    return ResponseEnvelope[EmbeddingProviderStatusResponse](success=True, data=status_resp, error=None)


@router.get(
    "/vector-search/status",
    response_model=ResponseEnvelope[VectorSearchStatusResponse],
    summary="Inspect MongoDB Atlas Vector Search index status and queryability safely",
)
async def get_vector_search_status_endpoint(
    db: Database = Depends(get_database),
):
    status_resp = embedding_service.get_atlas_vector_index_status(db)
    return ResponseEnvelope[VectorSearchStatusResponse](success=True, data=status_resp, error=None)


@router.post(
    "/search/vector",
    response_model=ResponseEnvelope[List[VectorSearchMatchItem]],
    summary="Semantic vector retrieval across incidents with strict tenant isolation",
)
async def vector_search_incidents_endpoint(
    query_text: str = Query(..., min_length=1, description="Diagnostic text or error description to embed"),
    project_id: str = Query(..., min_length=1, description="Active project ID"),
    allow_cross_project: bool = Query(default=False, description="Search public cross-project precedents"),
    has_cross_project_read: bool = Query(default=False, description="Server grant permitting cross-project memory read"),
    include_general_knowledge: bool = Query(default=False, description="Include curated general programming knowledge base matches"),
    limit: int = Query(default=5, ge=1, le=50, description="Max matches to return"),
    min_score: float = Query(default=0.50, ge=0.0, le=1.0, description="Minimum cosine similarity threshold"),
    db: Database = Depends(get_database),
):
    query_res = embedding_service.generate_query_embedding(query_text)
    matches = embedding_service.vector_search_incidents(
        db=db,
        query_vector=query_res.vector,
        project_id=project_id,
        allow_cross_project=allow_cross_project,
        has_cross_project_read=has_cross_project_read,
        include_general_knowledge=include_general_knowledge,
        limit=limit,
        min_score=min_score,
    )
    return ResponseEnvelope[List[VectorSearchMatchItem]](
        success=True,
        data=[VectorSearchMatchItem(**m) for m in matches],
        error=None,
    )


@router.post(
    "/backfill-embeddings",
    response_model=ResponseEnvelope[EmbeddingBackfillResponse],
    summary="Idempotently backfill embeddings for stored incidents missing vectors",
)
async def backfill_embeddings_endpoint(
    project_id: Optional[str] = Query(default=None, description="Scope backfill to specific project"),
    force: bool = Query(default=False, description="Force re-embedding existing documents"),
    db: Database = Depends(get_database),
):
    summary = embedding_service.backfill_incident_embeddings(db, project_id=project_id, force=force)
    return ResponseEnvelope[EmbeddingBackfillResponse](success=True, data=summary, error=None)


@router.post(
    "",
    response_model=ResponseEnvelope[IncidentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register an incident explicitly",
)
async def create_incident_endpoint(
    payload: IncidentCreate,
    db: Database = Depends(get_database),
):
    incident = incident_service.create_incident_direct(db, payload)
    return ResponseEnvelope[IncidentResponse](success=True, data=incident, error=None)


@router.get(
    "",
    response_model=ResponseEnvelope[PaginatedResponse[IncidentResponse]],
    summary="List incidents (all or filtered by project)",
)
async def list_incidents_endpoint(
    project_id: Optional[str] = Query(default=None, description="Filter by project ID"),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    db: Database = Depends(get_database),
):
    incidents = incident_service.list_incidents(
        db, project_id=project_id, limit=limit, skip=skip
    )
    return ResponseEnvelope[PaginatedResponse[IncidentResponse]](
        success=True, data=incidents, error=None
    )



@router.get(
    "/{incident_id}",
    response_model=ResponseEnvelope[IncidentResponse],
    summary="Get incident details by ID",
)
async def get_incident_endpoint(
    incident_id: str,
    db: Database = Depends(get_database),
):
    incident = incident_service.get_incident(db, incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )
    return ResponseEnvelope[IncidentResponse](success=True, data=incident, error=None)


@router.get(
    "/{incident_id}/history",
    response_model=ResponseEnvelope[IncidentHistoryResponse],
    summary="Retrieve same-project and privacy-sanitized cross-project historical matches",
)
async def get_incident_history_endpoint(
    incident_id: str,
    limit: int = Query(default=10, ge=1, le=50, description="Max matching incidents per partition"),
    db: Database = Depends(get_database),
):
    history = analytics_service.get_incident_history(db, incident_id=incident_id, limit=limit)
    return ResponseEnvelope[IncidentHistoryResponse](success=True, data=history, error=None)


# --- Diagnosis Endpoints ---


@router.post(
    "/{incident_id}/diagnosis",
    response_model=ResponseEnvelope[DiagnosisResponse],
    summary="Store structured AI diagnosis for an incident",
)
@router.post(
    "/{incident_id}/diagnoses",
    response_model=ResponseEnvelope[DiagnosisResponse],
    summary="Store structured AI diagnosis for an incident (plural alias)",
)
async def create_diagnosis_endpoint(
    incident_id: str,
    payload: DiagnosisCreate,
    response: Response,
    db: Database = Depends(get_database),
):
    diagnosis, is_new = diagnosis_service.create_diagnosis(db, incident_id=incident_id, payload=payload)
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return ResponseEnvelope[DiagnosisResponse](success=True, data=diagnosis, error=None)


@router.post(
    "/{incident_id}/diagnose",
    response_model=ResponseEnvelope[DiagnosisResponse],
    summary="Trigger AI diagnosis generation and persist result for an incident",
)
async def diagnose_incident_endpoint(
    incident_id: str,
    response: Response,
    allow_cross_project: bool = Query(default=True, description="Allow searching public cross-project precedents"),
    has_cross_project_read: bool = Query(default=False, description="Server permission for cross-project read"),
    disable_external_inference: Optional[bool] = Query(default=None, description="Force offline inference"),
    force_recheck: bool = Query(default=False, description="Force a new diagnosis even if one already exists"),
    db: Database = Depends(get_database),
):
    diagnosis, is_new = ai_service.generate_and_store_incident_diagnosis(
        db=db,
        incident_id=incident_id,
        allow_cross_project=allow_cross_project,
        has_cross_project_read=has_cross_project_read,
        disable_external_inference=disable_external_inference,
        force_recheck=force_recheck,
    )
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return ResponseEnvelope[DiagnosisResponse](success=True, data=diagnosis, error=None)


@router.get(
    "/{incident_id}/diagnosis",
    response_model=ResponseEnvelope[DiagnosisResponse],
    summary="Get the latest AI diagnosis for an incident",
)
@router.get(
    "/{incident_id}/diagnoses/latest",
    response_model=ResponseEnvelope[DiagnosisResponse],
    summary="Get the latest AI diagnosis for an incident (explicit path alias)",
)
async def get_latest_diagnosis_endpoint(
    incident_id: str,
    db: Database = Depends(get_database),
):
    diagnosis = diagnosis_service.get_latest_diagnosis(db, incident_id=incident_id)
    if not diagnosis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No diagnosis found for incident '{incident_id}'.",
        )
    return ResponseEnvelope[DiagnosisResponse](success=True, data=diagnosis, error=None)


@router.get(
    "/{incident_id}/diagnoses",
    response_model=ResponseEnvelope[PaginatedResponse[DiagnosisResponse]],
    summary="List paginated diagnosis history for an incident",
)
async def list_diagnoses_endpoint(
    incident_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    db: Database = Depends(get_database),
):
    diagnoses = diagnosis_service.list_incident_diagnoses(
        db, incident_id=incident_id, limit=limit, skip=skip
    )
    return ResponseEnvelope[PaginatedResponse[DiagnosisResponse]](
        success=True, data=diagnoses, error=None
    )


# --- Fix Outcome Endpoints ---


@router.post(
    "/{incident_id}/fixes",
    response_model=ResponseEnvelope[FixOutcomeResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a proposed fix for an incident",
)
async def create_fix_endpoint(
    incident_id: str,
    payload: FixOutcomeCreate,
    project_id: Optional[str] = Query(default=None, description="Project context of the requester"),
    db: Database = Depends(get_database),
):
    fix = fix_service.create_fix(db, incident_id=incident_id, payload=payload, project_id=project_id)
    return ResponseEnvelope[FixOutcomeResponse](success=True, data=fix, error=None)


@router.get(
    "/{incident_id}/fixes",
    response_model=ResponseEnvelope[PaginatedResponse[FixOutcomeResponse]],
    summary="List paginated fixes for an incident",
)
async def list_fixes_endpoint(
    incident_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    project_id: Optional[str] = Query(default=None, description="Project context of the requester"),
    db: Database = Depends(get_database),
):
    fixes = fix_service.list_incident_fixes(
        db, incident_id=incident_id, limit=limit, skip=skip, project_id=project_id
    )
    return ResponseEnvelope[PaginatedResponse[FixOutcomeResponse]](
        success=True, data=fixes, error=None
    )


@router.get(
    "/{incident_id}/fixes/verified",
    response_model=ResponseEnvelope[List[FixOutcomeResponse]],
    summary="List verified fixes for an incident",
)
async def get_verified_incident_fixes_endpoint(
    incident_id: str,
    project_id: Optional[str] = Query(default=None, description="Project context of the requester"),
    db: Database = Depends(get_database),
):
    fixes = fix_service.get_verified_fixes_for_incident(db, incident_id=incident_id, project_id=project_id)
    return ResponseEnvelope[List[FixOutcomeResponse]](success=True, data=fixes, error=None)


# --- Incident Embedding Endpoints ---


@router.get(
    "/{incident_id}/embedding",
    response_model=ResponseEnvelope[IncidentEmbeddingResponse],
    summary="Retrieve persisted embedding vector and metadata for an incident",
)
async def get_incident_embedding_endpoint(
    incident_id: str,
    db: Database = Depends(get_database),
):
    emb = embedding_service.get_incident_embedding(db, incident_id=incident_id)
    if not emb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No embedding found for incident '{incident_id}'.",
        )
    return ResponseEnvelope[IncidentEmbeddingResponse](success=True, data=emb, error=None)


@router.post(
    "/{incident_id}/embed",
    response_model=ResponseEnvelope[IncidentEmbeddingResponse],
    summary="Generate and persist embedding vector for an incident",
)
async def embed_incident_endpoint(
    incident_id: str,
    force: bool = Query(default=False, description="Force regenerate if embedding exists"),
    db: Database = Depends(get_database),
):
    emb = embedding_service.generate_and_persist_incident_embedding(db, incident_id=incident_id, force=force)
    if not emb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )
    return ResponseEnvelope[IncidentEmbeddingResponse](success=True, data=emb, error=None)
