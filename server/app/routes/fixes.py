"""Direct fix outcome retrieval and lifecycle updating API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas.fix import FixOutcomeResponse, FixOutcomeUpdate
from app.schemas import ResponseEnvelope
from app.services import fix_service

router = APIRouter(prefix="/fixes", tags=["Fix Outcomes"])


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
