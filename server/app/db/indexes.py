"""MongoDB collections, indexes, and schema validation initialization."""

import logging
from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)

PROJECTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["project_id", "name", "created_at", "updated_at"],
        "properties": {
            "project_id": {"bsonType": "string"},
            "name": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
        },
    }
}

COMMAND_RUNS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["event_id", "project_id", "command", "exit_code", "duration_ms", "created_at"],
        "properties": {
            "event_id": {"bsonType": "string"},
            "project_id": {"bsonType": "string"},
            "command": {"bsonType": "string"},
            "exit_code": {"bsonType": "int"},
            "duration_ms": {"bsonType": "int"},
            "created_at": {"bsonType": "date"},
        },
    }
}

INCIDENTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["incident_id", "project_id", "error_type", "error_message", "error_signature", "created_at"],
        "properties": {
            "incident_id": {"bsonType": "string"},
            "project_id": {"bsonType": "string"},
            "error_type": {"bsonType": "string"},
            "error_message": {"bsonType": "string"},
            "error_signature": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
            "embedding": {
                "bsonType": "array",
                "items": {"bsonType": ["double", "int"]},
            },
            "embedding_model": {"bsonType": "string"},
            "embedding_dimension": {"bsonType": "int"},
            "embedding_status": {"bsonType": "string"},
            "embedding_is_fallback": {"bsonType": "bool"},
            "embedding_canonical_text": {"bsonType": "string"},
            "embedded_at": {"bsonType": "date"},
        },
    }
}

DIAGNOSES_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["diagnosis_id", "incident_id", "project_id", "summary", "created_at"],
        "properties": {
            "diagnosis_id": {"bsonType": "string"},
            "incident_id": {"bsonType": "string"},
            "project_id": {"bsonType": "string"},
            "summary": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    }
}

FIX_OUTCOMES_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["fix_id", "incident_id", "project_id", "description", "status", "created_at", "updated_at"],
        "properties": {
            "fix_id": {"bsonType": "string"},
            "incident_id": {"bsonType": "string"},
            "project_id": {"bsonType": "string"},
            "diagnosis_id": {"bsonType": ["string", "null"]},
            "verification_event_id": {"bsonType": ["string", "null"]},
            "description": {"bsonType": "string"},
            "status": {
                "enum": ["proposed", "applied", "verifying", "verified", "failed", "reverted"]
            },
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
        },
    }
}

PERFORMANCE_RUNS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "event_id",
            "project_id",
            "command_signature",
            "duration_ms",
            "exit_code",
            "timestamp",
            "created_at",
        ],
        "properties": {
            "event_id": {"bsonType": "string"},
            "project_id": {"bsonType": "string"},
            "command_signature": {"bsonType": "string"},
            "command_label": {"bsonType": "string"},
            "duration_ms": {"bsonType": ["int", "long", "double"]},
            "exit_code": {"bsonType": "int"},
            "timestamp": {"bsonType": "date"},
            "regression_status": {
                "enum": ["unknown", "normal", "potential_regression"]
            },
            "baseline_duration_ms": {"bsonType": ["int", "long", "double", "null"]},
            "created_at": {"bsonType": "date"},
        },
    }
}

PERFORMANCE_BASELINES_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "project_id",
            "command_signature",
            "baseline_duration_ms",
            "sample_count",
            "calculated_at",
        ],
        "properties": {
            "project_id": {"bsonType": "string"},
            "command_signature": {"bsonType": "string"},
            "command_label": {"bsonType": "string"},
            "baseline_duration_ms": {"bsonType": ["int", "long", "double"]},
            "sample_count": {"bsonType": "int"},
            "calculated_at": {"bsonType": "date"},
        },
    }
}


def _ensure_collection_with_validator(db: Database, name: str, validator: dict) -> None:
    """Create collection with schema validator if missing, or update validator safely."""
    try:
        existing = db.list_collection_names()
        if name not in existing:
            db.create_collection(name, validator=validator)
            logger.info("Created collection '%s' with schema validator", name)
        else:
            try:
                db.command("collMod", name, validator=validator)
                logger.debug("Updated schema validator on collection '%s'", name)
            except OperationFailure:
                logger.debug("Skipped validator update for '%s' (insufficient permissions or unchanged)", name)
    except Exception as exc:
        logger.warning("Could not set validator for collection '%s': %s", name, exc)


def init_indexes(db: Database) -> None:
    """Initialize all required MongoDB collections, indexes, and validators idempotently."""
    logger.info("Initializing MongoDB indexes and schema validators...")

    # 1. Setup collections with validators
    _ensure_collection_with_validator(db, "projects", PROJECTS_VALIDATOR)
    _ensure_collection_with_validator(db, "command_runs", COMMAND_RUNS_VALIDATOR)
    _ensure_collection_with_validator(db, "incidents", INCIDENTS_VALIDATOR)
    _ensure_collection_with_validator(db, "diagnoses", DIAGNOSES_VALIDATOR)
    _ensure_collection_with_validator(db, "fix_outcomes", FIX_OUTCOMES_VALIDATOR)
    _ensure_collection_with_validator(db, "performance_runs", PERFORMANCE_RUNS_VALIDATOR)
    _ensure_collection_with_validator(db, "performance_baselines", PERFORMANCE_BASELINES_VALIDATOR)

    # 2. Projects indexes
    try:
        db.projects.create_index("project_id", unique=True, name="idx_projects_project_id_unique")
    except Exception as exc:
        logger.warning("Index error on projects: %s", exc)

    # 3. Command runs indexes
    try:
        db.command_runs.create_index("event_id", unique=True, name="idx_runs_event_id_unique")
        db.command_runs.create_index(
            [("project_id", ASCENDING), ("started_at", DESCENDING)],
            name="idx_runs_project_started_at",
        )
        db.command_runs.create_index(
            [("project_id", ASCENDING), ("exit_code", ASCENDING)],
            name="idx_runs_project_exit_code",
        )
    except Exception as exc:
        logger.warning("Index error on command_runs: %s", exc)

    # 4. Incidents indexes
    try:
        db.incidents.create_index("incident_id", unique=True, name="idx_incidents_incident_id_unique")
        db.incidents.create_index(
            [("project_id", ASCENDING), ("event_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"event_id": {"$type": "string"}},
            name="idx_incidents_project_event_unique",
        )
        db.incidents.create_index(
            [("project_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_incidents_project_created_at",
        )
        db.incidents.create_index(
            [("project_id", ASCENDING), ("error_signature", ASCENDING), ("created_at", DESCENDING)],
            name="idx_incidents_project_signature_created",
        )
        db.incidents.create_index(
            [("error_signature", ASCENDING), ("created_at", DESCENDING)],
            name="idx_incidents_signature_created",
        )
        db.incidents.create_index(
            [("diagnosis_status", ASCENDING), ("diagnosis_lease_expires_at", ASCENDING)],
            name="idx_incidents_status_lease",
        )
    except Exception as exc:
        logger.warning("Index error on incidents: %s", exc)

    # 5. Diagnoses indexes
    try:
        db.diagnoses.create_index("diagnosis_id", unique=True, name="idx_diagnoses_id_unique")
        db.diagnoses.create_index(
            [("incident_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_diagnoses_incident_created",
        )
    except Exception as exc:
        logger.warning("Index error on diagnoses: %s", exc)

    # 6. Fix outcomes indexes
    try:
        db.fix_outcomes.create_index("fix_id", unique=True, name="idx_fixes_id_unique")
        db.fix_outcomes.create_index(
            [("project_id", ASCENDING), ("incident_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_fixes_project_incident_created",
        )
        db.fix_outcomes.create_index(
            [("incident_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_fixes_incident_created",
        )
        db.fix_outcomes.create_index(
            [("status", ASCENDING), ("created_at", DESCENDING)],
            name="idx_fixes_status_created",
        )
        db.fix_outcomes.create_index(
            [("project_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
            name="idx_fixes_project_status_created",
        )
        db.fix_outcomes.create_index(
            [("diagnosis_id", ASCENDING)],
            name="idx_fixes_diagnosis_id",
            sparse=True,
        )
        db.fix_outcomes.create_index(
            [("verification_event_id", ASCENDING)],
            name="idx_fixes_event_id",
            sparse=True,
        )
    except Exception as exc:
        logger.warning("Index error on fix_outcomes: %s", exc)

    # 7. Performance runs indexes
    try:
        db.performance_runs.create_index("event_id", unique=True, name="idx_perf_event_id_unique")
        db.performance_runs.create_index(
            [("project_id", ASCENDING), ("timestamp", DESCENDING)],
            name="idx_perf_project_timestamp",
        )
        db.performance_runs.create_index(
            [("project_id", ASCENDING), ("command_signature", ASCENDING), ("timestamp", DESCENDING)],
            name="idx_perf_project_cmd_timestamp",
        )
        db.performance_runs.create_index(
            [("project_id", ASCENDING), ("regression_status", ASCENDING), ("timestamp", DESCENDING)],
            name="idx_perf_project_regression_timestamp",
        )
    except Exception as exc:
        logger.warning("Index error on performance_runs: %s", exc)

    # 8. Performance baselines indexes
    try:
        db.performance_baselines.create_index(
            [("project_id", ASCENDING), ("command_signature", ASCENDING)],
            unique=True,
            name="idx_perf_baselines_proj_cmd_unique",
        )
        db.performance_baselines.create_index(
            [("project_id", ASCENDING), ("calculated_at", DESCENDING)],
            name="idx_perf_baselines_proj_calculated",
        )
    except Exception as exc:
        logger.warning("Index error on performance_baselines: %s", exc)

    # 9. Atlas Vector Search index on incidents
    try:
        from app.services.embedding_service import ensure_atlas_vector_index
        ensure_atlas_vector_index(db)
    except Exception as exc:
        logger.debug("Atlas vector index check skipped or unsupported: %s", exc)

    logger.info("MongoDB indexes and collection validators verified successfully.")
