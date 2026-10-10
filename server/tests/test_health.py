"""Tests for DevMemory health endpoints and response envelopes."""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.routes.health import get_db_health


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health_healthy_root():
    """Verify /health returns 200 when database is healthy."""
    app.dependency_overrides[get_db_health] = lambda: True
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"] == {"application": "healthy", "database": "healthy"}
            assert data["error"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_health_healthy_versioned():
    """Verify /api/v1/health returns 200 when database is healthy."""
    app.dependency_overrides[get_db_health] = lambda: True
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"] == {"application": "healthy", "database": "healthy"}
            assert data["error"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_health_database_unavailable_root():
    """Verify /health returns 503 with proper envelope when database is down."""
    app.dependency_overrides[get_db_health] = lambda: False
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["success"] is False
            assert data["data"] == {"application": "healthy", "database": "unavailable"}
            assert data["error"] == "Database service unavailable"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_health_database_unavailable_versioned():
    """Verify /api/v1/health returns 503 with proper envelope when database is down."""
    app.dependency_overrides[get_db_health] = lambda: False
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/health")
            assert response.status_code == 503
            data = response.json()
            assert data["success"] is False
            assert data["data"] == {"application": "healthy", "database": "unavailable"}
            assert data["error"] == "Database service unavailable"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_openapi_docs_accessible():
    """Verify that OpenAPI documentation endpoint /docs loads successfully."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/docs")
        assert response.status_code == 200
