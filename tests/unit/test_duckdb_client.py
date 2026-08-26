# File: tests/unit/test_duckdb_client.py
"""Unit tests for DuckDB connection, repository, and DuckDBClient.

Validates schema initialization, single record upsert, batch upsert, pincode-based
spatial candidate filtering, and record count.
"""

from __future__ import annotations

import duckdb
import pytest

from app.db.duckdb_client import DuckDBClient
from app.db.repository import AddressRepository
from app.models.address import CanonicalAddress


class TestDuckDBRepository:
    """Test suite for AddressRepository."""

    def test_init_schema_and_upsert(
        self, in_memory_db: duckdb.DuckDBPyConnection, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Test schema initialization and upserting a record."""
        repo = AddressRepository()
        repo.init_schema(in_memory_db)
        repo.upsert_address(in_memory_db, sample_canonical_address)

        count = repo.count(in_memory_db)
        assert count == 1

        pool = repo.get_candidate_pool(in_memory_db, pincode="800001")
        assert len(pool) == 1
        assert pool[0]["sap_premise_id"] == sample_canonical_address.sap_premise_id

    def test_batch_upsert_and_filter(
        self, in_memory_db: duckdb.DuckDBPyConnection, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Test batch upsert of multiple records."""
        repo = AddressRepository()
        repo.init_schema(in_memory_db)

        # Create second record with different PIN
        slots_2 = sample_canonical_address.slots.model_copy(
            update={"pincode": "400001", "city": "mumbai"}
        )
        record_2 = CanonicalAddress(
            sap_premise_id="PR-400001-10-1A",
            full_address="10 Marine Drive, Flat 1A, Mumbai 400001",
            slots=slots_2,
            source_db="GIS_POSTGIS",
        )

        repo.batch_upsert(in_memory_db, [sample_canonical_address, record_2])
        assert repo.count(in_memory_db) == 2

        # Pincode filter returns only matching records
        pool_800001 = repo.get_candidate_pool(in_memory_db, pincode="800001")
        assert len(pool_800001) == 1
        assert pool_800001[0]["pincode"] == "800001"

        pool_400001 = repo.get_candidate_pool(in_memory_db, pincode="400001")
        assert len(pool_400001) == 1
        assert pool_400001[0]["pincode"] == "400001"


class TestDuckDBClientAsync:
    """Test suite for async DuckDBClient wrapper."""

    @pytest.mark.asyncio
    async def test_duckdb_client_async_methods(
        self, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Test async init_schema, upsert, count, and candidate pool queries."""
        client = DuckDBClient(":memory:")
        await client.init_schema()

        await client.upsert_address(sample_canonical_address)
        count = await client.count()
        assert count == 1

        pool = await client.get_candidate_pool(pincode="800001")
        assert len(pool) == 1
        assert pool[0]["sap_premise_id"] == "PR-800001-42-7B"

        client.close()
