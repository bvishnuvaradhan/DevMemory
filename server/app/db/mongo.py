"""MongoDB connection lifecycle manager and database accessor."""

import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from app.config import get_settings

logger = logging.getLogger(__name__)


class MongoManager:
    """Manages the MongoDB client connection lifecycle."""

    def __init__(self) -> None:
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None

    def connect(self) -> None:
        """Initialize MongoDB client without connecting at import time."""
        if self.client is not None:
            return

        settings = get_settings()
        logger.info("Initializing MongoDB client for database '%s'", settings.DATABASE_NAME)
        self.client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
            connect=False,
        )
        self.db = self.client[settings.DATABASE_NAME]

    def ping(self) -> bool:
        """Perform an active ping against MongoDB admin database."""
        if self.client is None:
            return False
        try:
            self.client.admin.command("ping")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as exc:
            logger.warning("MongoDB ping failed: %s", type(exc).__name__)
            return False

    def close(self) -> None:
        """Close MongoDB connection pool cleanly."""
        if self.client is not None:
            logger.info("Closing MongoDB client connection pool")
            self.client.close()
            self.client = None
            self.db = None

    def get_db(self) -> Database:
        """Return the active database instance.

        Raises:
            RuntimeError: If database connection has not been initialized.
        """
        if self.db is None:
            raise RuntimeError("Database connection has not been initialized.")
        return self.db


mongo_manager = MongoManager()


def get_database() -> Database:
    """FastAPI dependency to retrieve the active MongoDB database."""
    return mongo_manager.get_db()
