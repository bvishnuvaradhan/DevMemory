"""Service layer for performance measurement persistence, baselines, and regression analytics."""

from datetime import datetime, timezone
import statistics
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from pymongo import DESCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.config import get_settings
from app.schemas.pagination import PaginatedResponse
from app.schemas.performance import (
    CommandPerformanceSummary,
    PerformanceAnalyticsResponse,
    PerformanceBaselineResponse,
    PerformanceMeasurementCreate,
    PerformanceMeasurementResponse,
    RegressionStatus,
)
from app.utils.command_norm import compute_command_signature


def record_performance_measurement(
    db: Database, payload: PerformanceMeasurementCreate
) -> Tuple[PerformanceMeasurementResponse, bool]:
    """Record a command execution performance measurement with conflict detection and regression evaluation.

    Returns:
        (PerformanceMeasurementResponse, is_new: bool)
    """
    # 1. Verify project exists
    project = db.projects.find_one({"project_id": payload.project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{payload.project_id}' not found.",
        )

    # 2. Verify referenced command run exists
    run = db.command_runs.find_one({"event_id": payload.event_id})
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Referenced command run with event_id '{payload.event_id}' not found.",
        )

    # 3. Verify referenced run belongs to the same project
    if run["project_id"] != payload.project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Referenced run '{payload.event_id}' belongs to project '{run['project_id']}', "
                f"not requested project '{payload.project_id}'."
            ),
        )

    # 4. Resolve duration and validate non-negative
    duration_ms = payload.duration_ms if payload.duration_ms is not None else run.get("duration_ms", 0)
    if duration_ms < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="duration_ms must be non-negative.",
        )

    # 5. Resolve command string, exit code, timestamp, and environment
    cmd_str = payload.command or run.get("command") or ""
    exit_code = payload.exit_code if payload.exit_code is not None else run.get("exit_code", 0)
    timestamp = payload.timestamp or run.get("started_at") or run.get("created_at") or datetime.now(timezone.utc)
    environment = payload.environment or run.get("environment")

    # 6. Resolve command signature and label
    if payload.command_signature and payload.command_label:
        command_signature = payload.command_signature
        command_label = payload.command_label
    else:
        computed_sig, computed_label = compute_command_signature(cmd_str)
        command_signature = payload.command_signature or computed_sig
        command_label = payload.command_label or computed_label

    # 7. Evaluate regression status against current baseline
    settings = get_settings()
    baseline_doc = db.performance_baselines.find_one(
        {"project_id": payload.project_id, "command_signature": command_signature}
    )

    baseline_duration_ms: Optional[float] = None
    regression_status: RegressionStatus = RegressionStatus.UNKNOWN

    if baseline_doc and baseline_doc.get("baseline_duration_ms") is not None:
        baseline_duration_ms = float(baseline_doc["baseline_duration_ms"])
        if exit_code != 0:
            # Failed commands are not classified as proven performance regressions
            regression_status = RegressionStatus.UNKNOWN
        else:
            diff_ms = duration_ms - baseline_duration_ms
            pct_increase = (
                ((duration_ms - baseline_duration_ms) / baseline_duration_ms) * 100.0
                if baseline_duration_ms > 0
                else 0.0
            )
            if (
                pct_increase > settings.PERFORMANCE_REGRESSION_PERCENT_THRESHOLD
                and diff_ms > settings.PERFORMANCE_REGRESSION_ABS_MS_THRESHOLD
            ):
                regression_status = RegressionStatus.POTENTIAL_REGRESSION
            else:
                regression_status = RegressionStatus.NORMAL

    now = datetime.now(timezone.utc)
    doc = {
        "event_id": payload.event_id,
        "project_id": payload.project_id,
        "command_signature": command_signature,
        "command_label": command_label,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "timestamp": timestamp,
        "environment": environment.model_dump() if hasattr(environment, "model_dump") else environment,
        "baseline_duration_ms": baseline_duration_ms,
        "regression_status": regression_status.value,
        "created_at": now,
    }

    # 8. Race-safe atomic insert with conflict detection
    try:
        db.performance_runs.insert_one(doc)
    except DuplicateKeyError:
        existing = db.performance_runs.find_one({"event_id": payload.event_id}, {"_id": 0})
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Race condition encountered during performance measurement persistence.",
            )

        # Detect conflicting payload under identical event_id
        if (
            existing["project_id"] != payload.project_id
            or existing["command_signature"] != command_signature
            or existing["duration_ms"] != duration_ms
            or existing["exit_code"] != exit_code
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Conflict: event_id '{payload.event_id}' already exists with different measurement data "
                    f"(stored duration {existing['duration_ms']}ms, incoming {duration_ms}ms)."
                ),
            )

        # Idempotent retry: return existing measurement
        resp = PerformanceMeasurementResponse(**existing)
        resp.idempotent = True
        return resp, False

    resp = PerformanceMeasurementResponse(**doc)
    resp.idempotent = False
    return resp, True


def calculate_baseline(
    db: Database,
    project_id: str,
    command_signature: Optional[str] = None,
    min_samples: Optional[int] = None,
) -> PerformanceBaselineResponse:
    """Calculate and store a robust median performance baseline for comparable commands.

    Requires at least `min_samples` (default 5) valid successful observations.
    Does not fabricate a baseline if samples are insufficient.
    """
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    settings = get_settings()
    effective_min = min_samples if min_samples is not None else settings.PERFORMANCE_BASELINE_MIN_SAMPLES

    # Resolve target command signature if not provided
    target_signature = command_signature
    if not target_signature:
        latest_run = db.performance_runs.find_one(
            {"project_id": project_id, "exit_code": 0},
            sort=[("timestamp", DESCENDING)],
        )
        if latest_run:
            target_signature = latest_run["command_signature"]
        else:
            return PerformanceBaselineResponse(
                project_id=project_id,
                command_signature="",
                command_label="All commands",
                baseline_duration_ms=None,
                sample_count=0,
                min_samples_required=effective_min,
                status="insufficient_data",
                metric="median",
                calculated_at=datetime.now(timezone.utc),
                message=f"No successful runs found. At least {effective_min} successful runs required to establish a baseline.",
            )

    # Query valid successful observations for the signature
    query = {
        "project_id": project_id,
        "command_signature": target_signature,
        "exit_code": 0,
        "duration_ms": {"$gte": 0},
    }
    records = list(db.performance_runs.find(query).sort("timestamp", DESCENDING))
    sample_count = len(records)
    cmd_label = records[0].get("command_label", target_signature) if records else target_signature

    now = datetime.now(timezone.utc)

    # Check sufficient observations
    if sample_count < effective_min:
        return PerformanceBaselineResponse(
            project_id=project_id,
            command_signature=target_signature,
            command_label=cmd_label,
            baseline_duration_ms=None,
            sample_count=sample_count,
            min_samples_required=effective_min,
            status="insufficient_data",
            metric="median",
            calculated_at=now,
            message=(
                f"Insufficient samples ({sample_count}/{effective_min}). "
                f"At least {effective_min} successful runs required to establish a baseline."
            ),
        )

    # Calculate robust median and summary statistics
    durations = [r["duration_ms"] for r in records]
    median_val = statistics.median(durations)
    mean_val = statistics.mean(durations)
    min_val = min(durations)
    max_val = max(durations)

    baseline_doc = {
        "project_id": project_id,
        "command_signature": target_signature,
        "command_label": cmd_label,
        "baseline_duration_ms": round(float(median_val), 2),
        "sample_count": sample_count,
        "min_duration_ms": float(min_val),
        "max_duration_ms": float(max_val),
        "mean_duration_ms": round(float(mean_val), 2),
        "metric": "median",
        "calculated_at": now,
        "status": "established",
        "message": f"Baseline established using {sample_count} observations (median: {round(float(median_val), 2)}ms).",
    }

    # Upsert baseline record
    db.performance_baselines.update_one(
        {"project_id": project_id, "command_signature": target_signature},
        {"$set": baseline_doc},
        upsert=True,
    )

    return PerformanceBaselineResponse(**baseline_doc, min_samples_required=effective_min)


def get_project_baselines(
    db: Database, project_id: str, command_signature: Optional[str] = None
) -> List[PerformanceBaselineResponse]:
    """Retrieve established performance baselines for a project."""
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    query = {"project_id": project_id}
    if command_signature:
        query["command_signature"] = command_signature

    cursor = db.performance_baselines.find(query, {"_id": 0}).sort("calculated_at", DESCENDING)
    return [PerformanceBaselineResponse(**doc) for doc in cursor]


def list_performance_history(
    db: Database,
    project_id: str,
    limit: int = 50,
    skip: int = 0,
    command_signature: Optional[str] = None,
    regression_status: Optional[str] = None,
) -> PaginatedResponse[PerformanceMeasurementResponse]:
    """Retrieve paginated performance measurement history, newest first."""
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    query = {"project_id": project_id}
    if command_signature:
        query["command_signature"] = command_signature
    if regression_status:
        query["regression_status"] = regression_status

    total = db.performance_runs.count_documents(query)
    cursor = (
        db.performance_runs.find(query, {"_id": 0})
        .sort("timestamp", DESCENDING)
        .skip(skip)
        .limit(limit)
    )

    items = [PerformanceMeasurementResponse(**doc) for doc in cursor]
    return PaginatedResponse[PerformanceMeasurementResponse](
        items=items,
        total=total,
        limit=limit,
        skip=skip,
    )


def get_performance_analytics(db: Database, project_id: str) -> PerformanceAnalyticsResponse:
    """Calculate project-wide performance summary metrics and command-grouped breakdowns via MongoDB aggregation."""
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    pipeline = [
        {"$match": {"project_id": project_id}},
        {
            "$facet": {
                "overview": [
                    {
                        "$group": {
                            "_id": None,
                            "total_measurements": {"$sum": 1},
                            "successful_measurements": {
                                "$sum": {"$cond": [{"$eq": ["$exit_code", 0]}, 1, 0]}
                            },
                            "failed_measurements": {
                                "$sum": {"$cond": [{"$ne": ["$exit_code", 0]}, 1, 0]}
                            },
                            "average_duration_ms": {"$avg": "$duration_ms"},
                            "durations": {"$push": "$duration_ms"},
                            "potential_regressions_count": {
                                "$sum": {
                                    "$cond": [
                                        {"$eq": ["$regression_status", "potential_regression"]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "latest_measurement_at": {"$max": "$timestamp"},
                        }
                    }
                ],
                "by_command": [
                    {
                        "$group": {
                            "_id": "$command_signature",
                            "command_label": {"$first": "$command_label"},
                            "total_runs": {"$sum": 1},
                            "successful_runs": {
                                "$sum": {"$cond": [{"$eq": ["$exit_code", 0]}, 1, 0]}
                            },
                            "failed_runs": {
                                "$sum": {"$cond": [{"$ne": ["$exit_code", 0]}, 1, 0]}
                            },
                            "average_duration_ms": {"$avg": "$duration_ms"},
                            "durations": {"$push": "$duration_ms"},
                            "min_duration_ms": {"$min": "$duration_ms"},
                            "max_duration_ms": {"$max": "$duration_ms"},
                            "potential_regressions_count": {
                                "$sum": {
                                    "$cond": [
                                        {"$eq": ["$regression_status", "potential_regression"]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "latest_run_at": {"$max": "$timestamp"},
                            "latest_duration_ms": {"$last": "$duration_ms"},
                        }
                    },
                    {"$sort": {"total_runs": -1}},
                ],
            }
        },
    ]

    result = list(db.performance_runs.aggregate(pipeline))
    facet_data = result[0] if result else {"overview": [], "by_command": []}

    overview_list = facet_data.get("overview", [])
    if not overview_list:
        return PerformanceAnalyticsResponse(
            project_id=project_id,
            total_measurements=0,
            successful_measurements=0,
            failed_measurements=0,
            average_duration_ms=None,
            median_duration_ms=None,
            potential_regressions_count=0,
            latest_measurement_at=None,
            commands=[],
        )

    overview = overview_list[0]
    durations = overview.get("durations", [])
    median_duration = round(float(statistics.median(durations)), 2) if durations else None
    avg_duration = round(float(overview["average_duration_ms"]), 2) if overview.get("average_duration_ms") is not None else None

    # Load established baselines for comparison
    baselines_cursor = db.performance_baselines.find({"project_id": project_id})
    baseline_map = {b["command_signature"]: b.get("baseline_duration_ms") for b in baselines_cursor}

    command_summaries: List[CommandPerformanceSummary] = []
    for cmd in facet_data.get("by_command", []):
        cmd_sig = cmd["_id"]
        cmd_durations = cmd.get("durations", [])
        cmd_median = round(float(statistics.median(cmd_durations)), 2) if cmd_durations else None
        cmd_avg = round(float(cmd["average_duration_ms"]), 2) if cmd.get("average_duration_ms") is not None else None

        command_summaries.append(
            CommandPerformanceSummary(
                command_signature=cmd_sig,
                command_label=cmd.get("command_label", cmd_sig),
                total_runs=cmd["total_runs"],
                successful_runs=cmd["successful_runs"],
                failed_runs=cmd["failed_runs"],
                average_duration_ms=cmd_avg,
                median_duration_ms=cmd_median,
                min_duration_ms=cmd.get("min_duration_ms"),
                max_duration_ms=cmd.get("max_duration_ms"),
                potential_regressions_count=cmd.get("potential_regressions_count", 0),
                baseline_duration_ms=baseline_map.get(cmd_sig),
                latest_duration_ms=cmd.get("latest_duration_ms"),
                latest_run_at=cmd.get("latest_run_at"),
            )
        )

    return PerformanceAnalyticsResponse(
        project_id=project_id,
        total_measurements=overview["total_measurements"],
        successful_measurements=overview["successful_measurements"],
        failed_measurements=overview["failed_measurements"],
        average_duration_ms=avg_duration,
        median_duration_ms=median_duration,
        potential_regressions_count=overview["potential_regressions_count"],
        latest_measurement_at=overview.get("latest_measurement_at"),
        commands=command_summaries,
    )
