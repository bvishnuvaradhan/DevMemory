"""Read-only API routes for external LLM sanitized payload audits and frontend security evidence."""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas import ResponseEnvelope
from app.schemas.llm_audit import LLMRequestAuditItem, LLMSecuritySummary
from app.schemas.pagination import PaginatedResponse
from app.services import llm_audit_service

router = APIRouter(tags=["LLM Security Audits"])


def _verify_project_exists(db: Database, project_id: str) -> None:
    """Ensure the target project exists to provide clear 404 responses."""
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )


# ==============================================================================
# Nested Project-Scoped Endpoints: /api/v1/projects/{project_id}/llm-audits
# ==============================================================================

@router.get(
    "/projects/{project_id}/llm-audits/summary",
    response_model=ResponseEnvelope[LLMSecuritySummary],
    summary="Get project LLM outbound security monitor evidence summary",
)
async def get_project_llm_security_summary(
    project_id: str,
    db: Database = Depends(get_database),
):
    """Aggregate live security statistics directly from persisted LLM request audits."""
    _verify_project_exists(db, project_id)
    summary = llm_audit_service.get_project_security_summary(db, project_id=project_id)
    return ResponseEnvelope[LLMSecuritySummary](success=True, data=summary, error=None)


@router.get(
    "/projects/{project_id}/llm-audits",
    response_model=ResponseEnvelope[PaginatedResponse[LLMRequestAuditItem]],
    summary="List sanitized LLM request audits for project",
)
async def list_project_llm_audits(
    project_id: str,
    provider: Optional[str] = Query(default=None, description="Filter by LLM provider name"),
    transmission_status: Optional[str] = Query(
        default=None,
        description="Filter by status: prepared, dispatched, completed, failed, blocked_by_policy",
    ),
    incident_id: Optional[str] = Query(default=None, description="Filter by correlated incident ID"),
    start_date: Optional[datetime] = Query(default=None, description="Earliest creation timestamp"),
    end_date: Optional[datetime] = Query(default=None, description="Latest creation timestamp"),
    limit: int = Query(default=50, ge=1, le=100, description="Page limit"),
    skip: int = Query(default=0, ge=0, description="Items to skip"),
    db: Database = Depends(get_database),
):
    """Retrieve paginated list of audited sanitized payloads for a project."""
    _verify_project_exists(db, project_id)
    items, total = llm_audit_service.list_audits_for_project(
        db=db,
        project_id=project_id,
        provider=provider,
        transmission_status=transmission_status,
        incident_id=incident_id,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )
    paginated = PaginatedResponse[LLMRequestAuditItem](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )
    return ResponseEnvelope[PaginatedResponse[LLMRequestAuditItem]](
        success=True,
        data=paginated,
        error=None,
    )


@router.get(
    "/projects/{project_id}/llm-audits/{audit_id}",
    response_model=ResponseEnvelope[LLMRequestAuditItem],
    summary="Get single sanitized LLM audit item by ID",
)
async def get_project_llm_audit_item(
    project_id: str,
    audit_id: str,
    db: Database = Depends(get_database),
):
    """Retrieve full audit record strictly enforcing project ownership."""
    _verify_project_exists(db, project_id)
    audit = llm_audit_service.get_audit_by_id(db, project_id=project_id, audit_id=audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM audit record with ID '{audit_id}' not found for project '{project_id}'.",
        )
    return ResponseEnvelope[LLMRequestAuditItem](success=True, data=audit, error=None)


# ==============================================================================
# Top-Level Audits Endpoint: /api/v1/audits/llm
# ==============================================================================

@router.get(
    "/audits/llm/summary",
    response_model=ResponseEnvelope[LLMSecuritySummary],
    summary="Get LLM security evidence summary by query parameter",
)
async def get_llm_security_summary_query(
    project_id: str = Query(..., description="Project ID enforcing tenant isolation"),
    db: Database = Depends(get_database),
):
    _verify_project_exists(db, project_id)
    summary = llm_audit_service.get_project_security_summary(db, project_id=project_id)
    return ResponseEnvelope[LLMSecuritySummary](success=True, data=summary, error=None)


@router.get(
    "/audits/llm",
    response_model=ResponseEnvelope[PaginatedResponse[LLMRequestAuditItem]],
    summary="List LLM audits by project query parameter",
)
async def list_llm_audits_query(
    project_id: str = Query(..., description="Project ID enforcing tenant isolation"),
    provider: Optional[str] = Query(default=None, description="Filter by LLM provider name"),
    transmission_status: Optional[str] = Query(
        default=None,
        description="Filter by status: prepared, dispatched, completed, failed, blocked_by_policy",
    ),
    incident_id: Optional[str] = Query(default=None, description="Filter by correlated incident ID"),
    start_date: Optional[datetime] = Query(default=None, description="Earliest creation timestamp"),
    end_date: Optional[datetime] = Query(default=None, description="Latest creation timestamp"),
    limit: int = Query(default=50, ge=1, le=100, description="Page limit"),
    skip: int = Query(default=0, ge=0, description="Items to skip"),
    db: Database = Depends(get_database),
):
    _verify_project_exists(db, project_id)
    items, total = llm_audit_service.list_audits_for_project(
        db=db,
        project_id=project_id,
        provider=provider,
        transmission_status=transmission_status,
        incident_id=incident_id,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )
    paginated = PaginatedResponse[LLMRequestAuditItem](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )
    return ResponseEnvelope[PaginatedResponse[LLMRequestAuditItem]](
        success=True,
        data=paginated,
        error=None,
    )


@router.get(
    "/audits/llm/{audit_id}",
    response_model=ResponseEnvelope[LLMRequestAuditItem],
    summary="Get single LLM audit record by ID with project isolation",
)
async def get_llm_audit_query(
    audit_id: str,
    project_id: str = Query(..., description="Project ID enforcing tenant isolation"),
    db: Database = Depends(get_database),
):
    _verify_project_exists(db, project_id)
    audit = llm_audit_service.get_audit_by_id(db, project_id=project_id, audit_id=audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM audit record with ID '{audit_id}' not found for project '{project_id}'.",
        )
    return ResponseEnvelope[LLMRequestAuditItem](success=True, data=audit, error=None)
