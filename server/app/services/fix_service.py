"""Service layer for fix outcome lifecycle tracking and evidence verification."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import HTTPException, status
from pymongo import DESCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.schemas.fix import (
    FixOutcomeCreate,
    FixOutcomeResponse,
    FixOutcomeUpdate,
    FixVerificationRecordRequest,
)
from app.schemas.pagination import PaginatedResponse

# Valid status transitions state machine
ALLOWED_TRANSITIONS = {
    "proposed": {"applied", "verifying", "failed", "reverted"},
    "applied": {"verifying", "failed", "reverted"},
    "verifying": {"verified", "failed", "reverted"},
    "verified": {"reverted", "failed"},
    "failed": {"verifying", "proposed", "reverted"},
    "reverted": {"proposed", "verifying"},
}


def create_fix(
    db: Database,
    incident_id: str,
    payload: FixOutcomeCreate,
    project_id: Optional[str] = None,
) -> FixOutcomeResponse:
    """Register a proposed fix for an existing incident with resource validation."""
    incident = db.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    actual_project_id = incident["project_id"]
    if project_id and project_id != actual_project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Cannot create fix for incident belonging to project '{actual_project_id}' with project context '{project_id}'.",
        )

    # If diagnosis_id is provided, validate diagnosis existence and association
    if payload.diagnosis_id:
        diag = db.diagnoses.find_one({"diagnosis_id": payload.diagnosis_id})
        if not diag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Diagnosis with ID '{payload.diagnosis_id}' not found.",
            )
        if diag.get("incident_id") != incident_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Diagnosis '{payload.diagnosis_id}' belongs to incident '{diag.get('incident_id')}', not '{incident_id}'.",
            )
        if diag.get("project_id") != actual_project_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Diagnosis '{payload.diagnosis_id}' belongs to project '{diag.get('project_id')}', not '{actual_project_id}'.",
            )

    fix_id = payload.fix_id or f"fix_{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    doc = {
        "fix_id": fix_id,
        "incident_id": incident_id,
        "project_id": actual_project_id,
        "diagnosis_id": payload.diagnosis_id,
        "description": payload.description,
        "status": "proposed",
        "verification_method": None,
        "verification_command": None,
        "verification_exit_code": None,
        "verification_details": None,
        "verification_source": None,
        "verification_event_id": None,
        "verified_at": None,
        "created_at": now,
        "updated_at": now,
    }

    try:
        db.fix_outcomes.insert_one(doc)
    except DuplicateKeyError:
        existing = db.fix_outcomes.find_one({"fix_id": fix_id}, {"_id": 0})
        if existing:
            if existing.get("incident_id") != incident_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Fix ID '{fix_id}' already exists for another incident.",
                )
            return FixOutcomeResponse(**existing)
        raise

    return FixOutcomeResponse(**doc)


def get_fix(
    db: Database,
    fix_id: str,
    project_id: Optional[str] = None,
) -> Optional[FixOutcomeResponse]:
    """Retrieve a single fix outcome record by its ID with tenant isolation check."""
    doc = db.fix_outcomes.find_one({"fix_id": fix_id}, {"_id": 0})
    if not doc:
        return None

    if project_id and doc.get("project_id") != project_id:
        incident = db.incidents.find_one({"incident_id": doc.get("incident_id")})
        if not (incident and incident.get("is_public", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Fix '{fix_id}' belongs to project '{doc.get('project_id')}', not '{project_id}'.",
            )

    return FixOutcomeResponse(**doc)


def update_fix(
    db: Database,
    fix_id: str,
    payload: FixOutcomeUpdate,
    project_id: Optional[str] = None,
) -> FixOutcomeResponse:
    """Update fix outcome status and verification metadata adhering to evidence validation rules."""
    existing = db.fix_outcomes.find_one({"fix_id": fix_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fix with ID '{fix_id}' not found.",
        )

    if project_id and existing.get("project_id") != project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Cannot update fix belonging to project '{existing.get('project_id')}' with project context '{project_id}'.",
        )

    if payload.diagnosis_id is not None:
        diag = db.diagnoses.find_one({"diagnosis_id": payload.diagnosis_id})
        if not diag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Diagnosis with ID '{payload.diagnosis_id}' not found.",
            )
        if diag.get("incident_id") != existing.get("incident_id"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Diagnosis '{payload.diagnosis_id}' belongs to incident '{diag.get('incident_id')}', not '{existing.get('incident_id')}'.",
            )
        if diag.get("project_id") != existing.get("project_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Diagnosis '{payload.diagnosis_id}' belongs to project '{diag.get('project_id')}', not '{existing.get('project_id')}'.",
            )

    if payload.verification_event_id is not None:
        run = db.command_runs.find_one({"event_id": payload.verification_event_id})
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Command run with event_id '{payload.verification_event_id}' not found.",
            )
        if run.get("project_id") != existing.get("project_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Command run belongs to project '{run.get('project_id')}', but fix belongs to project '{existing.get('project_id')}'.",
            )

    current_status = existing["status"]
    target_status = payload.status or current_status

    # 1. Enforce status transition policy
    if target_status != current_status:
        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Invalid status transition from '{current_status}' to '{target_status}'. "
                    f"Allowed transitions: {sorted(list(allowed))}."
                ),
            )

    # 2. Strict Verification Evidence Rule:
    verified_at = existing.get("verified_at")
    if target_status == "verified":
        cmd = payload.verification_command or existing.get("verification_command")
        exit_code = (
            payload.verification_exit_code
            if payload.verification_exit_code is not None
            else existing.get("verification_exit_code")
        )
        source = (
            payload.verification_source
            or existing.get("verification_source")
            or ""
        ).strip().lower()
        method = (
            payload.verification_method
            or existing.get("verification_method")
            or ""
        ).strip().lower()
        details = (
            payload.verification_details
            or existing.get("verification_details")
            or ""
        ).strip()

        has_command_evidence = (
            cmd is not None and len(cmd.strip()) > 0 and exit_code == 0
        )
        has_user_evidence = (
            source == "user_confirmation" or method == "user_confirmation"
        ) and len(details) > 0

        if not (has_command_evidence or has_user_evidence):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cannot mark fix as verified without supporting verification evidence. "
                    "Provide either automated execution evidence (command with exit_code=0) "
                    "or explicit user confirmation with verification details."
                ),
            )

        verified_at = datetime.now(timezone.utc)
    elif target_status in ("reverted", "failed", "proposed"):
        # Reset verified_at if fix is reverted, failed, or reset
        verified_at = None

    now = datetime.now(timezone.utc)
    update_fields: Dict[str, Any] = {"updated_at": now}

    if payload.status is not None:
        update_fields["status"] = target_status
    if payload.description is not None:
        update_fields["description"] = payload.description
    if payload.diagnosis_id is not None:
        update_fields["diagnosis_id"] = payload.diagnosis_id
    if payload.verification_method is not None:
        update_fields["verification_method"] = payload.verification_method
    if payload.verification_command is not None:
        update_fields["verification_command"] = payload.verification_command
    if payload.verification_exit_code is not None:
        update_fields["verification_exit_code"] = payload.verification_exit_code
    if payload.verification_details is not None:
        update_fields["verification_details"] = payload.verification_details
    if payload.verification_source is not None:
        update_fields["verification_source"] = payload.verification_source
    if payload.verification_event_id is not None:
        update_fields["verification_event_id"] = payload.verification_event_id

    update_fields["verified_at"] = verified_at

    db.fix_outcomes.update_one({"fix_id": fix_id}, {"$set": update_fields})

    updated_doc = db.fix_outcomes.find_one({"fix_id": fix_id}, {"_id": 0})
    return FixOutcomeResponse(**updated_doc)


def list_incident_fixes(
    db: Database,
    incident_id: str,
    limit: int = 50,
    skip: int = 0,
    project_id: Optional[str] = None,
) -> PaginatedResponse[FixOutcomeResponse]:
    """Retrieve paginated fixes for a specific incident sorted newest first with tenant isolation check."""
    incident = db.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    if project_id and incident.get("project_id") != project_id:
        if not incident.get("is_public", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Incident '{incident_id}' belongs to project '{incident.get('project_id')}', not '{project_id}'.",
            )

    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    filter_query = {"incident_id": incident_id}
    total = db.fix_outcomes.count_documents(filter_query)
    cursor = (
        db.fix_outcomes.find(filter_query, {"_id": 0})
        .sort("created_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    items = [FixOutcomeResponse(**d) for d in cursor]

    return PaginatedResponse[FixOutcomeResponse](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )


def record_fix_verification(
    db: Database,
    fix_id: str,
    payload: FixVerificationRecordRequest,
    project_id: Optional[str] = None,
) -> FixOutcomeResponse:
    """Record execution results for an automated or manual fix verification command.

    Security & Integrity Guarantees:
    1. Tenant Isolation: If project_id is provided, enforces that the caller has access to the fix's project.
    2. Trusted Execution Verification: If payload.event_id is provided, resolves the trusted command_runs
       record from the database, validates project association, and uses the recorded exit_code (preventing forged claims).
    3. Caller Attestation Guard: Caller-supplied exit_code 0 alone (without event_id, command, or details)
       is rejected with HTTP 422. Manual or CI attestation without a recorded event_id is labeled
       'caller_attestation' or 'user_confirmation', never falsely masquerading as an internal platform runner.
    4. State Consistency: exit_code == 0 marks status='verified' with timestamp; non-zero marks status='failed'
       and resets verified_at to None.
    """
    existing = db.fix_outcomes.find_one({"fix_id": fix_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fix with ID '{fix_id}' not found.",
        )

    # 1. Enforce tenant isolation
    if project_id and existing.get("project_id") != project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Cannot verify fix belonging to project '{existing.get('project_id')}' with project context '{project_id}'.",
        )

    # 2. Validate incident association
    incident = db.incidents.find_one({"incident_id": existing.get("incident_id")})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Associated incident '{existing.get('incident_id')}' not found.",
        )

    now = datetime.now(timezone.utc)
    event_id = payload.event_id

    # 3. Trusted execution mechanism vs Caller attestation
    if event_id:
        run = db.command_runs.find_one({"event_id": event_id})
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Command run with event_id '{event_id}' not found in execution history.",
            )
        # Validate that the run belongs to the same project as the fix
        if run.get("project_id") != existing.get("project_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Command run belongs to project '{run.get('project_id')}', but fix belongs to project '{existing.get('project_id')}'.",
            )
        # Use trusted actual execution result from database (prevents caller from forging exit_code 0)
        actual_exit_code = run.get("exit_code", payload.exit_code)
        cmd = run.get("command", payload.command or "")
        details = payload.details or run.get("stdout") or run.get("stderr") or f"Recorded run '{cmd}' exited with code {actual_exit_code}."
        method = "recorded_command_run"
        source = "devmemory_runner"
    else:
        # Caller attestation path
        cmd = (payload.command or "").strip()
        details = (payload.details or "").strip()
        source_in = (payload.source or "").strip().lower()

        # Caller-supplied exit_code 0 alone must not be treated as independently verified proof
        if payload.exit_code == 0:
            if not cmd and not details:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Caller-supplied exit_code 0 alone is insufficient for verification. "
                        "Provide verifiable execution details/command or reference a recorded event_id."
                    ),
                )
            if source_in in ("user_confirmation", "manual", "developer_attestation"):
                method = "user_confirmation"
                source = payload.source or "user_confirmation"
            else:
                method = "caller_attestation"
                # Prevent caller from falsely claiming internal runner without an event_id
                if source_in in ("devmemory_runner", "recorded_command_run"):
                    source = "attested_execution"
                else:
                    source = payload.source or "caller_attestation"
        else:
            method = "caller_attestation"
            source = payload.source or "caller_attestation"

        actual_exit_code = payload.exit_code
        cmd = payload.command
        details = payload.details

    # 4. State transition and timestamp consistency
    if actual_exit_code == 0:
        new_status = "verified"
        verified_at = now
    else:
        new_status = "failed"
        verified_at = None

    update_fields = {
        "status": new_status,
        "verification_method": method,
        "verification_command": cmd,
        "verification_exit_code": actual_exit_code,
        "verification_details": details,
        "verification_source": source,
        "verification_event_id": event_id,
        "verified_at": verified_at,
        "updated_at": now,
    }

    db.fix_outcomes.update_one({"fix_id": fix_id}, {"$set": update_fields})
    updated_doc = db.fix_outcomes.find_one({"fix_id": fix_id}, {"_id": 0})
    return FixOutcomeResponse(**updated_doc)


def get_verified_fixes_for_incident(
    db: Database,
    incident_id: str,
    project_id: Optional[str] = None,
) -> List[FixOutcomeResponse]:
    """Retrieve all verified fixes for a specific incident with tenant isolation checks."""
    incident = db.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    # Tenant isolation validation: if caller provides project context, check access
    if project_id and incident.get("project_id") != project_id:
        if not incident.get("is_public", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Incident '{incident_id}' belongs to project '{incident.get('project_id')}', not '{project_id}'.",
            )

    cursor = (
        db.fix_outcomes.find(
            {
                "incident_id": incident_id,
                "status": "verified",
                "verified_at": {"$ne": None},
            },
            {"_id": 0},
        )
        .sort([("verified_at", DESCENDING), ("created_at", DESCENDING)])
    )
    return [FixOutcomeResponse(**d) for d in cursor]


def query_verified_fixes(
    db: Database,
    error_signature: Optional[str] = None,
    project_id: Optional[str] = None,
    allow_cross_project: bool = False,
    has_cross_project_read: bool = False,
    limit: int = 20,
) -> List[FixOutcomeResponse]:
    """Query verified fixes across incidents for recommendation and learning with tenant isolation.

    Guarantees:
    1. If project_id is provided, validates that the project exists.
    2. Without cross-project authorization, returns ONLY verified fixes belonging to that project_id.
    3. If cross-project read is authorized, includes other projects' fixes ONLY if their incidents are marked is_public=True.
    4. If project_id is omitted, strictly restricts retrieval to incidents marked is_public=True (never leaking private tenant fixes).
    5. Excludes any unverified, failed, or revoked fixes (status must be 'verified' and verified_at not None).
    """
    limit = max(1, min(limit, 100))

    if project_id:
        proj = db.projects.find_one({"project_id": project_id})
        if not proj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID '{project_id}' not found.",
            )

        if allow_cross_project and has_cross_project_read:
            inc_filter: Dict[str, Any] = {
                "$or": [{"project_id": project_id}, {"is_public": True}]
            }
        else:
            inc_filter = {"project_id": project_id}

        if error_signature:
            inc_filter["error_signature"] = error_signature

        incidents = list(db.incidents.find(inc_filter, {"incident_id": 1, "_id": 0}))
        incident_ids = [inc["incident_id"] for inc in incidents]
        if not incident_ids:
            return []

        fix_filter: Dict[str, Any] = {
            "incident_id": {"$in": incident_ids},
            "status": "verified",
            "verified_at": {"$ne": None},
        }
    else:
        # Cross-project query without tenant context: strictly restricted to public incidents
        inc_filter = {"is_public": True}
        if error_signature:
            inc_filter["error_signature"] = error_signature

        public_incidents = list(db.incidents.find(inc_filter, {"incident_id": 1, "_id": 0}))
        public_inc_ids = [inc["incident_id"] for inc in public_incidents]
        if not public_inc_ids:
            return []

        fix_filter = {
            "incident_id": {"$in": public_inc_ids},
            "status": "verified",
            "verified_at": {"$ne": None},
        }

    cursor = (
        db.fix_outcomes.find(fix_filter, {"_id": 0})
        .sort([("verified_at", DESCENDING), ("created_at", DESCENDING)])
        .limit(limit)
    )
    return [FixOutcomeResponse(**d) for d in cursor]


def list_fixes(
    db: Database,
    project_id: Optional[str] = None,
    incident_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
) -> PaginatedResponse[FixOutcomeResponse]:
    """Retrieve paginated fixes across all projects or filtered by project/incident ID."""
    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    filter_query: dict = {}
    if project_id:
        filter_query["project_id"] = project_id
    if incident_id:
        filter_query["incident_id"] = incident_id

    total = db.fix_outcomes.count_documents(filter_query)
    cursor = (
        db.fix_outcomes.find(filter_query, {"_id": 0})
        .sort("created_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    items = [FixOutcomeResponse(**d) for d in cursor]

    return PaginatedResponse[FixOutcomeResponse](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )
