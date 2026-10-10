"""Direct fix outcome retrieval, verification recording, and lifecycle updating API routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas.fix import (
    FixOutcomeResponse,
    FixOutcomeUpdate,
    FixVerificationRecordRequest,
)
from app.schemas import ResponseEnvelope
from app.services import fix_service

router = APIRouter(prefix="/fixes", tags=["Fix Outcomes"])


@router.get(
    "/verified",
    response_model=ResponseEnvelope[List[FixOutcomeResponse]],
    summary="Query verified successful fixes for recommendations",
)
async def query_verified_fixes_endpoint(
    error_signature: Optional[str] = Query(default=None, description="Filter by error signature"),
    project_id: Optional[str] = Query(default=None, description="Filter by project ID"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of verified fixes to return"),
    db: Database = Depends(get_database),
):
    fixes = fix_service.query_verified_fixes(
        db,
        error_signature=error_signature,
        project_id=project_id,
        limit=limit,
    )
    return ResponseEnvelope[List[FixOutcomeResponse]](success=True, data=fixes, error=None)


@router.get(
    "/{fix_id}",
    response_model=ResponseEnvelope[FixOutcomeResponse],
    summary="Get fix details by ID",
)
async def get_fix_endpoint(
    fix_id: str,
    db: Database = Depends(get_database),
):
    fix = fix_service.get_fix(db, fix_id)
    if not fix:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fix with ID '{fix_id}' not found.",
        )
    return ResponseEnvelope[FixOutcomeResponse](success=True, data=fix, error=None)


@router.patch(
    "/{fix_id}",
    response_model=ResponseEnvelope[FixOutcomeResponse],
    summary="Update fix status and record verification evidence",
)
async def update_fix_endpoint(
    fix_id: str,
    payload: FixOutcomeUpdate,
    db: Database = Depends(get_database),
):
    updated = fix_service.update_fix(db, fix_id=fix_id, payload=payload)
    return ResponseEnvelope[FixOutcomeResponse](success=True, data=updated, error=None)


@router.post(
    "/{fix_id}/verify",
    response_model=ResponseEnvelope[FixOutcomeResponse],
    summary="Record verification test execution results for a fix",
)
async def record_fix_verification_endpoint(
    fix_id: str,
    payload: FixVerificationRecordRequest,
    db: Database = Depends(get_database),
):
    updated = fix_service.record_fix_verification(db, fix_id=fix_id, payload=payload)
    return ResponseEnvelope[FixOutcomeResponse](success=True, data=updated, error=None)
