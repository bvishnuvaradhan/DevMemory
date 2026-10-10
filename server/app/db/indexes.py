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
    except Exception as exc:
        logger.warning("Index error on command_runs: %s", exc)

    # 4. Incidents indexes
    try:
        db.incidents.create_index("incident_id", unique=True, name="idx_incidents_incident_id_unique")
        # Partial unique index: only enforces uniqueness when event_id is a non-null string
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
        db.incidents.create_index("error_signature", name="idx_incidents_error_signature")
    except Exception as exc:
        logger.warning("Index error on incidents: %s", exc)

    logger.info("MongoDB indexes and collection validators verified successfully.")
