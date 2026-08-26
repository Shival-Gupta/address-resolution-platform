# File: tests/integration/test_hybrid_router.py
"""Integration tests for full 4-Tier HybridRouter cascade resolution.

Validates that all 8 address permutation patterns resolve to the exact same
SAP Premise ID through the cascade.
"""

from __future__ import annotations

import pytest

from app.db.duckdb_client import DuckDBClient
from app.db.mock_data import generate_permutations
from app.engines.hybrid_router import HybridRouter
from app.models.address import CanonicalAddress
from app.models.search import SearchQuery


class TestHybridRouterIntegration:
    """Integration test suite for HybridRouter."""

    @pytest.mark.asyncio
    async def test_all_eight_permutations_resolve_to_same_sap_id(
        self, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Verify all 8 address permutations resolve to the exact same SAP Premise ID."""
        db_client = DuckDBClient(":memory:")
        await db_client.init_schema()
        await db_client.upsert_address(sample_canonical_address)

        router = HybridRouter(db_client=db_client)
        permutations = generate_permutations(sample_canonical_address)

        for perm in permutations:
            query = SearchQuery(raw_address=perm["input"])
            result = await router.resolve(query)

            # Candidate pool should contain the target record
            matching_candidates = [
                c
                for c in result.candidates
                if c.sap_premise_id == sample_canonical_address.sap_premise_id
            ]
            assert len(matching_candidates) >= 1, f"Failed to match candidate for {perm['type']}"

            # If resolved, it must match expected SAP ID
            if result.resolved:
                assert result.resolved.sap_premise_id == sample_canonical_address.sap_premise_id, (
                    f"Mismatch for permutation type {perm['type']}"
                )

        db_client.close()
