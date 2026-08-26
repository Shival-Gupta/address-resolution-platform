# File: tests/unit/test_mock_data.py
"""Unit tests for synthetic address generation and DuckDB insertion.

Validates deterministic generation with seed, structure of the 8 canonical
permutations per address, and DuckDB schema initialization and data insertion.
"""

from __future__ import annotations

import random

import duckdb

from app.db.mock_data import (
    generate_canonical_address,
    generate_permutations,
    init_duckdb_schema,
    insert_canonical_addresses,
)


class TestMockData:
    """Test suite for mock data generator."""

    def test_deterministic_generation(self) -> None:
        """Test that same seed produces identical address objects."""
        rng1 = random.Random(42)
        addr1 = generate_canonical_address(rng1)

        rng2 = random.Random(42)
        addr2 = generate_canonical_address(rng2)

        assert addr1.sap_premise_id == addr2.sap_premise_id
        assert addr1.full_address == addr2.full_address
        assert addr1.slots.pincode == addr2.slots.pincode
        assert addr1.slots.premise_number == addr2.slots.premise_number
        assert addr1.slots.flat_no == addr2.slots.flat_no

    def test_eight_permutations_generation(self) -> None:
        """Test generating exactly 8 permutation variants for an address."""
        rng = random.Random(123)
        addr = generate_canonical_address(rng)
        permutations = generate_permutations(addr)

        assert len(permutations) == 8
        types = [p["type"] for p in permutations]
        expected_types = [
            "p1_canonical",
            "p2_abbreviated",
            "p3_jumbled_order",
            "p4_prefix_flat",
            "p5_compact_slash",
            "p6_state_country_code",
            "p7_missing_pincode",
            "p8_phonetic_typo",
        ]
        assert types == expected_types

        # Every permutation must map to the same expected SAP ID
        for p in permutations:
            assert p["expected_sap_id"] == addr.sap_premise_id
            assert len(p["input"]) > 5

    def test_duckdb_insertion_and_querying(self) -> None:
        """Test inserting generated addresses into an in-memory DuckDB table."""
        conn = duckdb.connect(":memory:")
        init_duckdb_schema(conn)

        rng = random.Random(99)
        addresses = [generate_canonical_address(rng) for _ in range(50)]

        insert_canonical_addresses(conn, addresses)

        count = conn.execute("SELECT COUNT(*) FROM addresses").fetchone()[0]
        assert count == 50

        # Query by pincode
        first_pin = addresses[0].slots.pincode
        matching = conn.execute(
            "SELECT sap_premise_id, full_address FROM addresses WHERE pincode = ?",
            [first_pin],
        ).fetchall()
        assert len(matching) >= 1

        conn.close()
