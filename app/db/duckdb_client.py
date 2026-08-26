# File: app/db/duckdb_client.py
"""Async-compatible DuckDB client managing database lifecycle and repository queries.

Provides async wrappers around DuckDB connection management and schema operations,
designed for FastAPI dependency injection and batch pipelines.
"""

from __future__ import annotations

import asyncio
from typing import Any

import duckdb

from app.db.connection import get_connection
from app.db.repository import AddressRepository
from app.models.address import CanonicalAddress


class DuckDBClient:
    """Async-compatible client wrapper for DuckDB database operations.

    DuckDB connections are NOT thread-safe for concurrent access.
    This client serializes all connection access via a threading.Lock,
    allowing safe use with asyncio.to_thread() under FastAPI's concurrent request handling.

    For production scale (> 50 concurrent search requests), migrate to a connection pool
    pattern (one connection per thread) or switch Tier 1 to Typesense/Elasticsearch.
    """

    def __init__(
        self, db_path: str = ":memory:", conn: duckdb.DuckDBPyConnection | None = None
    ) -> None:
        """Initialize DuckDBClient with file path or optional existing connection.

        Args:
            db_path: Path to database file or ':memory:'.
            conn: Optional pre-existing DuckDB connection (e.g. for testing).
        """
        import threading

        self.db_path = db_path
        self._conn = conn or get_connection(db_path)
        self._repo = AddressRepository()
        self._lock = threading.Lock()

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """Return the underlying DuckDB connection."""
        return self._conn

    async def init_schema(self) -> None:
        """Initialize table schema and spatial indices."""
        await asyncio.to_thread(self._locked_init_schema)

    def _locked_init_schema(self) -> None:
        with self._lock:
            self._repo.init_schema(self._conn)

    async def upsert_address(self, record: CanonicalAddress) -> None:
        """Insert or update a single canonical address record.

        Args:
            record: CanonicalAddress instance.
        """
        await asyncio.to_thread(self._locked_upsert, record)

    def _locked_upsert(self, record: CanonicalAddress) -> None:
        with self._lock:
            self._repo.upsert_address(self._conn, record)

    async def batch_upsert(self, records: list[CanonicalAddress]) -> None:
        """Insert or update multiple canonical address records in bulk.

        Args:
            records: List of CanonicalAddress instances.
        """
        await asyncio.to_thread(self._locked_batch_upsert, records)

    def _locked_batch_upsert(self, records: list[CanonicalAddress]) -> None:
        with self._lock:
            self._repo.batch_upsert(self._conn, records)

    async def get_candidate_pool(
        self, pincode: str | None, limit: int = 15000
    ) -> list[dict[Any, Any]]:
        """Retrieve candidate pool pre-filtered by PIN code.

        Args:
            pincode: 6-digit postal code, or None.
            limit: Maximum records to return.

        Returns:
            list[dict[str, Any]]: List of matching candidate records.
        """
        return await asyncio.to_thread(self._locked_get_pool, pincode, limit)

    def _locked_get_pool(self, pincode: str | None, limit: int) -> list[dict[Any, Any]]:
        with self._lock:
            return self._repo.get_candidate_pool(self._conn, pincode, limit)

    async def count(self) -> int:
        """Return total record count in addresses table.

        Returns:
            int: Number of address records.
        """
        return await asyncio.to_thread(self._locked_count)

    def _locked_count(self) -> int:
        with self._lock:
            return self._repo.count(self._conn)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
