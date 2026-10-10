"""Incident registration and retrieval API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas.incident import IncidentCreate, IncidentResponse
from app.schemas import ResponseEnvelope
from app.services import incident_service

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
