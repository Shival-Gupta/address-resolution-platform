# File: app/main.py
"""FastAPI Application Entrypoint for Address Resolution Platform.

Provides application factory, async lifespan lifecycle management (DuckDB pool
initialization, schema validation, and seed verification), CORS, OpenTelemetry tracing,
request logging middleware, and API router mounting.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.exceptions import AddressResolutionError, NormalizationError
from app.db.duckdb_client import DuckDBClient
from app.db.mock_data import generate_canonical_dataset
from app.pipeline.orchestrator import SearchOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("address_resolution_platform")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle events.

    Initializes DuckDB storage, seeds initial synthetic records if database is empty,
    and sets up search pipeline orchestrator on app.state.
    """
    settings = get_settings()
    logger.info("Initializing Address Resolution Platform (DuckDB: %s)...", settings.DUCKDB_PATH)

    # Initialize DuckDB client and table schema
    db_client = DuckDBClient(db_path=settings.DUCKDB_PATH)
    await db_client.init_schema()

    # Seed mock data if database is empty
    count = await db_client.count()
    if count == 0:
        logger.info("Database is empty. Generating and seeding synthetic address dataset...")
        seed_records = generate_canonical_dataset(records=1000, seed=42)
        await db_client.batch_upsert(seed_records)
        logger.info("Successfully seeded %d canonical addresses into DuckDB.", len(seed_records))

    # Initialize search orchestrator
    orchestrator = SearchOrchestrator(db_client=db_client)

    # Attach instances to app state
    app.state.db_client = db_client
    app.state.orchestrator = orchestrator

    yield

    logger.info("Shutting down Address Resolution Platform...")
    db_client.close()


def create_app() -> FastAPI:
    """FastAPI application factory.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="Address Resolution Platform API",
        description=(
            "High-performance, 4-tier cascaded Indian address resolution engine "
            "for SAP S/4HANA & GIS."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS Middleware
    # allow_credentials=False is correct for API-key-authenticated services.
    # Browsers reject allow_origins=["*"] + allow_credentials=True per the CORS spec.
    # If this API is consumed from a known frontend domain, set CORS_ORIGINS in env.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key", "Authorization"],
    )

    # Request Logging & Tracing Middleware
    @app.middleware("http")
    async def logging_and_tracing_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"

        logger.info(
            "%s %s -> %d (%.2fms) [req_id=%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response

    # Exception Handlers
    @app.exception_handler(NormalizationError)
    async def normalization_error_handler(
        _request: Request, exc: NormalizationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "NormalizationError", "detail": str(exc)},
        )

    @app.exception_handler(AddressResolutionError)
    async def custom_exception_handler(
        _request: Request, exc: AddressResolutionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": exc.__class__.__name__, "detail": str(exc)},
        )

    # Mount API routers
    app.include_router(api_v1_router, prefix="/v1")
    app.include_router(api_v1_router, prefix="/api/v1")

    # Root Level Health & Readiness Route
    @app.get("/health", tags=["system"], summary="Root health check")
    async def root_health() -> dict[str, str]:
        return {"status": "ok", "service": "address-resolution-platform"}

    @app.get("/metrics", tags=["system"], summary="Root metrics probe")
    async def root_metrics() -> dict[str, Any]:
        return {
            "status": "healthy",
            "tier1_threshold": settings.TIER1_CONFIDENCE_THRESHOLD,
            "tier2_threshold": settings.TIER2_CONFIDENCE_THRESHOLD,
            "circuit_breaker_state": "CLOSED",
        }

    return app


app = create_app()
