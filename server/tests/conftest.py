"""Pytest fixtures for DevMemory backend testing."""

import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import MongoClient

from app.config import get_settings
from app.db.indexes import init_indexes
from app.db.mongo import get_database
from app.main import app

TEST_DB_NAME = "devmemory_test"


@pytest.fixture(scope="session")
def test_mongo_client():
    """Session fixture providing a live MongoDB client for isolated test database."""
    settings = get_settings()
    client = MongoClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    )
    try:
        client.admin.command("ping")
    except Exception as exc:
        pytest.skip(f"Live MongoDB not reachable at {settings.MONGODB_URI}: {exc}")

    yield client

    client.drop_database(TEST_DB_NAME)
    client.close()


@pytest.fixture(autouse=True)
def test_db(test_mongo_client):
    """Function-level fixture ensuring clean collections for each test."""
    db = test_mongo_client[TEST_DB_NAME]
    for col in ["projects", "command_runs", "incidents", "diagnoses", "fix_outcomes"]:
        db[col].delete_many({})

    init_indexes(db)
    app.dependency_overrides[get_database] = lambda: db
    yield db
    app.dependency_overrides.pop(get_database, None)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_client():
    """Async HTTP client bound to the FastAPI application without bubbling unhandled exceptions."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        yield client
