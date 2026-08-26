# File: app/db/repository.py
"""DuckDB repository for executing parameterized address queries and mutations.

Manages schema initialization, index creation, record upserts, pincode-based
spatial candidate filtering, and premise/flat number lookups.
"""

from __future__ import annotations

from typing import Any

import duckdb

from app.models.address import CanonicalAddress


class AddressRepository:
    """Repository handling SQL operations against DuckDB address tables."""

    @staticmethod
    def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
        """Initialize the addresses table and associated indexes.

        Args:
            conn: Active DuckDB connection.
        """
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS addresses (
                sap_premise_id   VARCHAR PRIMARY KEY,
                full_address     VARCHAR NOT NULL,
                pincode          VARCHAR(6),
                premise_number   VARCHAR,
                flat_no          VARCHAR,
                street           VARCHAR,
                city             VARCHAR,
                state            VARCHAR,
                normalized_str   VARCHAR,
                embedding        FLOAT[768],
                geohash          VARCHAR,
                source_db        VARCHAR,
                created_at       TIMESTAMP,
                updated_at       TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_pincode ON addresses(pincode);
            CREATE INDEX IF NOT EXISTS idx_premise ON addresses(pincode, premise_number, flat_no);
            """
        )

    @staticmethod
    def upsert_address(conn: duckdb.DuckDBPyConnection, record: CanonicalAddress) -> None:
        """Insert or replace a single canonical address record.

        Args:
            conn: Active DuckDB connection.
            record: CanonicalAddress model instance.
        """
        s = record.slots
        conn.execute(
            """
            INSERT OR REPLACE INTO addresses (
                sap_premise_id, full_address, pincode, premise_number,
                flat_no, street, city, state, normalized_str,
                embedding, geohash, source_db, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record.sap_premise_id,
                record.full_address,
                s.pincode,
                s.premise_number,
                s.flat_no,
                s.street,
                s.city,
                s.state,
                " ".join(s.normalized_tokens),
                record.embedding,
                record.geohash,
                record.source_db,
                record.created_at,
                record.updated_at,
            ],
        )

    @staticmethod
    def batch_upsert(conn: duckdb.DuckDBPyConnection, records: list[CanonicalAddress]) -> None:
        """Insert or replace multiple canonical address records in a single transaction.

        Args:
            conn: Active DuckDB connection.
            records: List of CanonicalAddress model instances.
        """
        if not records:
            return

        rows = [
            (
                r.sap_premise_id,
                r.full_address,
                r.slots.pincode,
                r.slots.premise_number,
                r.slots.flat_no,
                r.slots.street,
                r.slots.city,
                r.slots.state,
                " ".join(r.slots.normalized_tokens),
                r.embedding,
                r.geohash,
                r.source_db,
                r.created_at,
                r.updated_at,
            )
            for r in records
        ]

        conn.executemany(
            """
            INSERT OR REPLACE INTO addresses (
                sap_premise_id, full_address, pincode, premise_number,
                flat_no, street, city, state, normalized_str,
                embedding, geohash, source_db, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    @staticmethod
    def get_candidate_pool(
        conn: duckdb.DuckDBPyConnection, pincode: str | None, limit: int = 15000
    ) -> list[dict[str, Any]]:
        """Retrieve candidate addresses pre-filtered by 6-digit postal code.

        Args:
            conn: Active DuckDB connection.
            pincode: 6-digit PIN code to filter by, or None for global fallback.
            limit: Maximum candidate records to fetch.

        Returns:
            list[dict[str, Any]]: List of address record dictionaries.
        """
        columns = [
            "sap_premise_id",
            "full_address",
            "pincode",
            "premise_number",
            "flat_no",
            "street",
            "city",
            "state",
            "normalized_str",
            "embedding",
            "geohash",
            "source_db",
        ]
        select_cols = ", ".join(columns)

        if pincode:
            query = f"SELECT {select_cols} FROM addresses WHERE pincode = ? LIMIT ?"
            result = conn.execute(query, [pincode, limit]).fetchall()
        else:
            query = f"SELECT {select_cols} FROM addresses LIMIT ?"
            result = conn.execute(query, [limit]).fetchall()

        return [dict(zip(columns, row, strict=False)) for row in result]

    @staticmethod
    def count(conn: duckdb.DuckDBPyConnection) -> int:
        """Return the total number of records stored in the addresses table.

        Args:
            conn: Active DuckDB connection.

        Returns:
            int: Record count.
        """
        row = conn.execute("SELECT COUNT(*) FROM addresses").fetchone()
        return int(row[0]) if row else 0
