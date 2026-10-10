"""DevMemory FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.db.indexes import init_indexes
from app.db.mongo import mongo_manager
from app.routes.fixes import router as fixes_router
from app.routes.health import router as health_router
from app.routes.incidents import router as incidents_router
from app.routes.projects import router as projects_router
from app.routes.runs import router as runs_router
from app.schemas import ResponseEnvelope

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("devmemory.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    settings = get_settings()
    logger.info("DevMemory API initializing on %s:%s", settings.API_HOST, settings.API_PORT)
    mongo_manager.connect()
    if mongo_manager.ping():
        logger.info("Active MongoDB connection verified")
        try:
            init_indexes(mongo_manager.get_db())
        except Exception as exc:
            logger.warning("Failed to initialize indexes during startup: %s", exc)
    else:
        logger.warning("MongoDB ping failed during startup - database service is unavailable")

    yield

    logger.info("DevMemory API shutting down...")
    mongo_manager.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title="DevMemory API",
        description="Persistent developer memory and troubleshooting platform backend API.",
        version="0.4.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # HTTPException handler returning consistent envelope
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        envelope = ResponseEnvelope[None](
            success=False,
            data=None,
            error=str(exc.detail),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope.model_dump(),
        )

    # RequestValidationError handler returning consistent 422 envelope
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        error_messages = "; ".join(
            [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
        )
        envelope = ResponseEnvelope[None](
            success=False,
            data=None,
            error=f"Validation failed: {error_messages}",
        )
        return JSONResponse(
            status_code=422,
            content=envelope.model_dump(),
        )

    # PyMongoError exception handler to safely mask connection strings and tracebacks
    @app.exception_handler(PyMongoError)
    async def pymongo_exception_handler(request: Request, exc: PyMongoError) -> JSONResponse:
        logger.error(
            "Database error on %s %s: %s",
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        envelope = ResponseEnvelope[None](
            success=False,
            data=None,
            error="Database error occurred",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=envelope.model_dump(),
        )

    # Global unhandled exception handler
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        envelope = ResponseEnvelope[None](
            success=False,
            data=None,
            error="Internal server error",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=envelope.model_dump(),
        )

    # Register routers
    app.include_router(health_router)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(incidents_router, prefix="/api/v1")
    app.include_router(fixes_router, prefix="/api/v1")

    return app


app = create_app()
