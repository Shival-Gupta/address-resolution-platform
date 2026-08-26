# File: app/db/connection.py
"""DuckDB connection lifecycle and context management.

Provides helper utilities for managing DuckDB database connections in both
file-backed and in-memory configurations.
"""

from __future__ import annotations

from pathlib import Path

import duckdb


def get_connection(db_path: str = ":memory:", read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Create and return a configured DuckDB database connection.

    Args:
        db_path: Path to database file or ':memory:'.
        read_only: Whether to open the database in read-only mode.

    Returns:
        duckdb.DuckDBPyConnection: Active connection instance.
    """
    if db_path != ":memory:":
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

    return duckdb.connect(database=db_path, read_only=read_only)
