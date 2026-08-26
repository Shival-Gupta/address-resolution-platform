# File: app/api/deps.py
"""FastAPI dependency injection providers for database and pipeline orchestrators.

Provides request-scoped dependency providers for accessing application-wide
DuckDB clients, search orchestrators, and security validators.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.auth import verify_admin_key, verify_api_key
from app.core.config import Settings, get_settings
from app.db.duckdb_client import DuckDBClient
from app.pipeline.orchestrator import SearchOrchestrator


def get_db(request: Request, settings: Settings = Depends(get_settings)) -> DuckDBClient:
    """Retrieve or construct the DuckDBClient instance from application state.

    Args:
        request: Inbound FastAPI request.
        settings: Application settings.

    Returns:
        DuckDBClient: Initialized DuckDB client.
    """
    if hasattr(request.app.state, "db_client") and request.app.state.db_client is not None:
        client: DuckDBClient = request.app.state.db_client
        return client
    return DuckDBClient(db_path=settings.DUCKDB_PATH)


def get_orchestrator(
    request: Request, db_client: DuckDBClient = Depends(get_db)
) -> SearchOrchestrator:
    """Retrieve or construct the SearchOrchestrator from application state.

    Args:
        request: Inbound FastAPI request.
        db_client: Injected DuckDB client.

    Returns:
        SearchOrchestrator: Ready-to-use search pipeline orchestrator.
    """
    if hasattr(request.app.state, "orchestrator") and request.app.state.orchestrator is not None:
        orch: SearchOrchestrator = request.app.state.orchestrator
        return orch
    return SearchOrchestrator(db_client=db_client)


__all__ = [
    "get_db",
    "get_orchestrator",
    "get_settings",
    "verify_admin_key",
    "verify_api_key",
]
