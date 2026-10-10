"""Tests for database failure handling and secret safety."""

import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock
from pymongo.errors import ConnectionFailure

from app.db.mongo import get_database
from app.main import app


@pytest.mark.anyio
async def test_mongo_failure_safe_handling(async_client: AsyncClient):
    """Scenario 17: Database failure returns 500 without leaking connection URI or tracebacks."""
    mock_db = MagicMock()
    mock_db.projects.insert_one.side_effect = ConnectionFailure(
        "mongodb://user:secret@db.internal:27017 connection failed"
    )

    app.dependency_overrides[get_database] = lambda: mock_db
    try:
        response = await async_client.post(
            "/api/v1/projects",
            json={"name": "Critical Service", "project_id": "proj_critical"},
        )
        assert response.status_code == 500
        body = response.json()
        assert body["success"] is False
        assert body["data"] is None
        # Strict security check: sensitive connection string and credentials MUST NOT be leaked
        assert "secret" not in body["error"]
        assert "mongodb://" not in body["error"]
        assert "Database error occurred" in body["error"]
    finally:
        app.dependency_overrides.pop(get_database, None)
