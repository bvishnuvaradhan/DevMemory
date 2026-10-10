"""Incident registration, retrieval, historical memory, diagnosis, and fix tracking API routes."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas.analytics import IncidentHistoryResponse
from app.schemas.diagnosis import DiagnosisCreate, DiagnosisResponse
from app.schemas.fix import FixOutcomeCreate, FixOutcomeResponse
from app.schemas.incident import IncidentCreate, IncidentResponse
from app.schemas.pagination import PaginatedResponse
from app.schemas import ResponseEnvelope
from app.services import ai_service, analytics_service, diagnosis_service, fix_service, incident_service

router = APIRouter(prefix="/incidents", tags=["Incidents"])


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
    db: Database = Depends(get_database),
):
    diagnosis, is_new = ai_service.generate_and_store_incident_diagnosis(
        db=db,
        incident_id=incident_id,
        allow_cross_project=allow_cross_project,
        has_cross_project_read=has_cross_project_read,
        disable_external_inference=disable_external_inference,
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
    db: Database = Depends(get_database),
):
    fix = fix_service.create_fix(db, incident_id=incident_id, payload=payload)
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
    db: Database = Depends(get_database),
):
    fixes = fix_service.list_incident_fixes(
        db, incident_id=incident_id, limit=limit, skip=skip
    )
    return ResponseEnvelope[PaginatedResponse[FixOutcomeResponse]](
        success=True, data=fixes, error=None
    )
