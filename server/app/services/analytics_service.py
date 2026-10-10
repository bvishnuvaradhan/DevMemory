"""Service layer for MongoDB aggregation pipelines, analytics, and privacy-aware history retrieval."""

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from pymongo import DESCENDING
from pymongo.database import Database

from app.schemas.analytics import (
    CrossProjectIncidentSummary,
    IncidentHistoryResponse,
    ProjectAnalyticsResponse,
    RecurringErrorItem,
    RecurringErrorsResponse,
)
from app.schemas.incident import IncidentResponse
from app.utils.signature import sanitize_error_message


def get_recurring_errors(
    db: Database,
    project_id: str,
    limit: int = 10,
) -> RecurringErrorsResponse:
    """Execute MongoDB aggregation pipeline to group and rank recurring incidents by error signature."""
    # 1. Verify project exists
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    limit = max(1, min(limit, 50))

    # 2. Aggregation pipeline
    pipeline = [
        {
            "$match": {
                "project_id": project_id,
                "error_signature": {"$exists": True, "$ne": None, "$ne": ""},
            }
        },
        {
            "$group": {
                "_id": "$error_signature",
                "occurrence_count": {"$sum": 1},
                "latest_occurrence": {"$max": "$created_at"},
                "error_type": {"$first": "$error_type"},
                "representative_message": {"$first": "$error_message"},
            }
        },
        {
            "$sort": {
                "occurrence_count": -1,
                "latest_occurrence": -1,
            }
        },
        {
            "$limit": limit,
        },
        {
            "$project": {
                "_id": 0,
                "error_signature": "$_id",
                "error_type": 1,
                "error_message": "$representative_message",
                "occurrence_count": 1,
                "latest_occurrence": 1,
            }
        },
    ]

    results = list(db.incidents.aggregate(pipeline))

    # Calculate total distinct groups
    count_pipeline = [
        {
            "$match": {
                "project_id": project_id,
                "error_signature": {"$exists": True, "$ne": None, "$ne": ""},
            }
        },
        {"$group": {"_id": "$error_signature"}},
        {"$count": "total"},
    ]
    count_res = list(db.incidents.aggregate(count_pipeline))
    total_groups = count_res[0]["total"] if count_res else 0

    return RecurringErrorsResponse(
        items=[RecurringErrorItem(**r) for r in results],
        total_groups=total_groups,
    )


def get_project_analytics(
    db: Database,
    project_id: str,
) -> ProjectAnalyticsResponse:
    """Calculate high-level performance and stability metrics for a project."""
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    # 1. Run stats pipeline
    run_pipeline = [
        {"$match": {"project_id": project_id}},
        {
            "$group": {
                "_id": None,
                "total_runs": {"$sum": 1},
                "successful_runs": {
                    "$sum": {"$cond": [{"$eq": ["$exit_code", 0]}, 1, 0]}
                },
                "failed_runs": {
                    "$sum": {"$cond": [{"$ne": ["$exit_code", 0]}, 1, 0]}
                },
                "avg_duration": {"$avg": "$duration_ms"},
            }
        },
    ]

    run_stats = list(db.command_runs.aggregate(run_pipeline))
    if run_stats:
        total_runs = run_stats[0]["total_runs"]
        successful_runs = run_stats[0]["successful_runs"]
        failed_runs = run_stats[0]["failed_runs"]
        avg_dur = (
            int(round(run_stats[0]["avg_duration"]))
            if run_stats[0]["avg_duration"] is not None
            else None
        )
    else:
        total_runs = successful_runs = failed_runs = 0
        avg_dur = None

    # 2. Incident stats
    total_incidents = db.incidents.count_documents({"project_id": project_id})
    distinct_signatures = len(
        db.incidents.distinct("error_signature", {"project_id": project_id})
    )

    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_24h = db.incidents.count_documents({
        "project_id": project_id,
        "created_at": {"$gte": cutoff_24h},
    })

    return ProjectAnalyticsResponse(
        project_id=project_id,
        total_runs=total_runs,
        successful_runs=successful_runs,
        failed_runs=failed_runs,
        total_incidents=total_incidents,
        distinct_error_signatures=distinct_signatures,
        recent_incidents_24h=recent_24h,
        average_duration_ms=avg_dur,
    )


def get_incident_history(
    db: Database,
    incident_id: str,
    limit: int = 10,
) -> IncidentHistoryResponse:
    """Retrieve historical incidents partitioned into same-project and privacy-sanitized cross-project results."""
    # 1. Retrieve target incident
    current = db.incidents.find_one({"incident_id": incident_id}, {"_id": 0})
    if not current:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    target_sig = current["error_signature"]
    target_proj = current["project_id"]
    limit = max(1, min(limit, 50))

    # 2. Query same-project historical matches (excluding self)
    same_proj_cursor = (
        db.incidents.find(
            {
                "project_id": target_proj,
                "error_signature": target_sig,
                "incident_id": {"$ne": incident_id},
            },
            {"_id": 0},
        )
        .sort("created_at", DESCENDING)
        .limit(limit)
    )
    same_project_matches = [IncidentResponse(**doc) for doc in same_proj_cursor]

    # 3. Query cross-project matches (strictly from other projects)
    cross_proj_cursor = (
        db.incidents.find(
            {
                "project_id": {"$ne": target_proj},
                "error_signature": target_sig,
            },
            {"_id": 0},
        )
        .sort("created_at", DESCENDING)
        .limit(limit)
    )

    # Sanitize and construct cross-project summaries:
    # Explicitly omit private local paths, snippets, and unredacted sensitive tokens
    cross_project_matches = []
    for doc in cross_proj_cursor:
        sanitized_msg = sanitize_error_message(doc.get("error_message", ""))
        summary = CrossProjectIncidentSummary(
            incident_id=doc["incident_id"],
            project_id=doc["project_id"],
            error_type=doc["error_type"],
            error_signature=doc["error_signature"],
            error_message=sanitized_msg,
            created_at=doc["created_at"],
            diagnosis_summary=doc.get("diagnosis_summary"),
            fix_status=doc.get("fix_status"),
        )
        cross_project_matches.append(summary)

    return IncidentHistoryResponse(
        current_incident_id=incident_id,
        error_signature=target_sig,
        same_project_matches=same_project_matches,
        cross_project_matches=cross_project_matches,
    )
