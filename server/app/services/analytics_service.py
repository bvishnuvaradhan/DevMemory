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


def get_global_overview(db: Database) -> dict:
    """Aggregate platform-wide telemetry, project summaries, and recurring error clusters."""
    total_projects = db.projects.count_documents({})
    total_runs = db.command_runs.count_documents({})
    total_failures = db.command_runs.count_documents({"exit_code": {"$ne": 0}})
    failure_rate = (
        f"{(total_failures / total_runs * 100):.1f}%" if total_runs > 0 else "0.0%"
    )
    verified_fixes = db.fix_outcomes.count_documents({"status": "verified"})
    total_fixes = db.fix_outcomes.count_documents({})
    verified_fix_rate = (
        f"{(verified_fixes / total_fixes * 100):.1f}%" if total_fixes > 0 else "0.0%"
    )

    # Recurring errors count: signatures with > 1 occurrence
    rec_pipe = [
        {"$match": {"error_signature": {"$exists": True, "$ne": None, "$ne": ""}}},
        {"$group": {"_id": "$error_signature", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$count": "total"},
    ]
    rec_res = list(db.incidents.aggregate(rec_pipe))
    recurring_errors_count = rec_res[0]["total"] if rec_res else 0

    # Median execution time in ms
    durations = [
        r["duration_ms"]
        for r in db.command_runs.find({}, {"duration_ms": 1, "_id": 0})
        if r.get("duration_ms") is not None
    ]
    durations.sort()
    median_dur = durations[len(durations) // 2] if durations else 0

    active_incidents_count = db.incidents.count_documents({})

    stats = {
        "totalProjects": total_projects,
        "totalRuns": total_runs,
        "totalFailures": total_failures,
        "failureRate": failure_rate,
        "verifiedFixes": verified_fixes,
        "verifiedFixRate": verified_fix_rate,
        "recurringErrorsCount": recurring_errors_count,
        "medianExecutionTimeMs": median_dur,
        "activeIncidentsCount": active_incidents_count,
        "isMock": False,
    }

    # 1. Batch aggregate command_runs per project in a single query
    run_stats_pipe = [
        {
            "$group": {
                "_id": "$project_id",
                "total_runs": {"$sum": 1},
                "failures": {"$sum": {"$cond": [{"$ne": ["$exit_code", 0]}, 1, 0]}},
                "last_run_at": {"$max": "$started_at"},
                "durations": {"$push": "$duration_ms"},
            }
        }
    ]
    run_stats = {r["_id"]: r for r in db.command_runs.aggregate(run_stats_pipe)}

    # 2. Batch aggregate verified fixes per project in a single query
    fix_stats_pipe = [
        {"$match": {"status": "verified"}},
        {"$group": {"_id": "$project_id", "verified_fixes": {"$sum": 1}}},
    ]
    fix_stats = {r["_id"]: r["verified_fixes"] for r in db.fix_outcomes.aggregate(fix_stats_pipe)}

    # 3. Retrieve projects sorted newest first
    projects_cursor = db.projects.find({}, {"_id": 0}).sort("created_at", DESCENDING).limit(50)
    projects = []
    for p in projects_cursor:
        pid = p.get("project_id")
        r_stat = run_stats.get(pid, {})
        durs = [d for d in r_stat.get("durations", []) if d is not None]
        durs.sort()
        proj_median = durs[len(durs) // 2] if durs else 0
        last_ts = r_stat.get("last_run_at")
        last_ts_iso = (
            last_ts.isoformat()
            if hasattr(last_ts, "isoformat")
            else str(last_ts)
            if last_ts
            else None
        )
        total_p_runs = r_stat.get("total_runs", 0)
        p_fails = r_stat.get("failures", 0)
        p_doc = {
            "id": pid,
            "project_id": pid,
            "name": p.get("name") or pid,
            "description": p.get("description", ""),
            "language": p.get("language", ""),
            "framework": p.get("framework", ""),
            "repository": p.get("repository", ""),
            "totalRuns": total_p_runs,
            "failureCount": p_fails,
            "verifiedFixCount": fix_stats.get(pid, 0),
            "lastRunAt": last_ts_iso,
            "lastRunStatus": (
                "failure"
                if p_fails > 0
                else ("success" if total_p_runs > 0 else "unknown")
            ),
            "medianDurationMs": proj_median,
        }
        projects.append(p_doc)

    # Recent runs
    recent_runs_cursor = (
        db.command_runs.find({}, {"_id": 0})
        .sort("started_at", DESCENDING)
        .limit(10)
    )
    recent_runs = []
    performance_trend = []
    for r in recent_runs_cursor:
        ts = r.get("started_at")
        ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None
        recent_runs.append({
            "eventId": r.get("event_id"),
            "projectId": r.get("project_id"),
            "projectName": r.get("project_id"),
            "command": r.get("command"),
            "exitCode": r.get("exit_code"),
            "status": r.get("status"),
            "durationMs": r.get("duration_ms"),
            "timestamp": ts_iso,
            "errorSummary": r.get("stderr") or r.get("stdout") or None,
        })
        if ts and r.get("duration_ms") is not None:
            time_label = ts.strftime("%H:%M") if hasattr(ts, "strftime") else str(ts)[11:16]
            performance_trend.append({
                "timestamp": time_label,
                "durationMs": r.get("duration_ms"),
                "medianMs": median_dur,
                "baselineMs": median_dur,
            })
    performance_trend.reverse()

    # Recurring error clusters
    verified_incident_ids = db.fix_outcomes.distinct("incident_id", {"status": "verified"})
    verified_sigs = (
        set(
            db.incidents.distinct(
                "error_signature",
                {"incident_id": {"$in": verified_incident_ids}},
            )
        )
        if verified_incident_ids
        else set()
    )

    rec_list_pipe = [
        {"$match": {"error_signature": {"$exists": True, "$ne": None, "$ne": ""}}},
        {
            "$group": {
                "_id": "$error_signature",
                "count": {"$sum": 1},
                "error_type": {"$first": "$error_type"},
                "error_message": {"$first": "$error_message"},
                "affected_projects": {"$addToSet": "$project_id"},
                "latest_occurrence": {"$max": "$created_at"},
                "first_seen": {"$min": "$created_at"},
            }
        },
        {"$sort": {"count": -1, "latest_occurrence": -1}},
        {"$limit": 5},
    ]
    recurring_errors = []
    for r in db.incidents.aggregate(rec_list_pipe):
        sig = r["_id"]
        latest = r.get("latest_occurrence")
        latest_iso = latest.isoformat() if hasattr(latest, "isoformat") else str(latest) if latest else None
        first = r.get("first_seen")
        first_iso = first.isoformat() if hasattr(first, "isoformat") else str(first) if first else None
        aff_projs = [p for p in r.get("affected_projects", []) if p]
        has_fix = sig in verified_sigs
        err_msg = r.get("error_message") or ""
        err_type = r.get("error_type") or "Error"

        recurring_errors.append({
            "errorSignature": sig,
            "error_signature": sig,
            "errorType": err_type,
            "error_type": err_type,
            "category": "Runtime Failure",
            "sampleMessage": err_msg,
            "error_message": err_msg,
            "errorMessage": err_msg,
            "occurrences": r.get("count", 1),
            "occurrence_count": r.get("count", 1),
            "count": r.get("count", 1),
            "affectedProjects": aff_projs if aff_projs else ["default"],
            "affected_projects": aff_projs,
            "hasVerifiedFix": has_fix,
            "has_verified_fix": has_fix,
            "latestOccurrence": latest_iso,
            "latest_occurrence": latest_iso,
            "firstSeen": first_iso,
        })


    # Verified fixes
    fixes_cursor = (
        db.fix_outcomes.find({"status": "verified"}, {"_id": 0})
        .sort("verified_at", DESCENDING)
        .limit(5)
    )
    verified_fixes = []
    for f in fixes_cursor:
        v_at = f.get("verified_at")
        v_iso = v_at.isoformat() if hasattr(v_at, "isoformat") else str(v_at) if v_at else None
        verified_fixes.append({
            "id": f.get("fix_id"),
            "fixId": f.get("fix_id"),
            "projectId": f.get("project_id"),
            "projectName": f.get("project_id"),
            "errorType": "Resolved Issue",
            "solutionSummary": f.get("description"),
            "verificationMethod": f.get("verification_command") or f.get("verification_method"),
            "testResult": f.get("verification_details") or "Verified successfully",
            "status": "VERIFIED",
            "verifiedAt": v_iso,
        })

    return {
        "stats": stats,
        "projects": projects,
        "recentRuns": recent_runs,
        "recurringErrors": recurring_errors,
        "verifiedFixes": verified_fixes,
        "performanceTrend": performance_trend,
    }


def get_events(
    db: Database,
    project_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    """Retrieve chronologically sorted audit event stream across runs, diagnoses, and fixes."""
    limit = max(1, min(limit, 100))
    skip = max(0, skip)

    filter_query: dict = {}
    if project_id:
        filter_query["project_id"] = project_id

    # 1. Runs as events
    run_cursor = (
        db.command_runs.find(filter_query, {"_id": 0})
        .sort("started_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    events = []
    for r in run_cursor:
        is_success = r.get("exit_code") == 0
        ts = r.get("started_at")
        ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None
        summary = (
            f"Command '{r.get('command')}' completed successfully (exit 0)"
            if is_success
            else f"Command '{r.get('command')}' failed with exit code {r.get('exit_code')}"
        )
        events.append({
            "eventId": r.get("event_id"),
            "timestamp": ts_iso,
            "projectId": r.get("project_id"),
            "projectName": r.get("project_id"),
            "eventType": "COMMAND_RUN",
            "status": "SUCCESS" if is_success else "FAILED",
            "summary": summary,
            "relatedCommand": r.get("command"),
            "relatedIncidentId": r.get("incident_id"),
            "sourceLocation": None,
            "details": f"Duration: {r.get('duration_ms')}ms. {r.get('stderr') or r.get('stdout') or ''}".strip(),
        })

    # Sort descending by timestamp
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return events[:limit]
