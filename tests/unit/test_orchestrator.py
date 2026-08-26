# File: tests/unit/test_orchestrator.py
"""Unit tests for SearchOrchestrator and HybridRouter cascade lifecycle.

Validates Tier 0 -> Tier 1 -> Tier 2 -> Tier 3 execution flow, auto-resolve
confidence thresholds, missing pincode degradation, tier limiting, and typeahead suggest.
"""

from __future__ import annotations

import pytest

from app.db.duckdb_client import DuckDBClient
from app.models.address import CanonicalAddress
from app.models.search import SearchQuery
from app.pipeline.orchestrator import SearchOrchestrator


class TestSearchOrchestrator:
    """Test suite for SearchOrchestrator cascade lifecycle."""

    @pytest.mark.asyncio
    async def test_high_confidence_tier1_auto_resolves_early(
        self, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Verify queries with >= 0.92 Tier 1 confidence resolve without invoking Tier 2 or 3."""
        db_client = DuckDBClient(":memory:")
        await db_client.init_schema()
        await db_client.upsert_address(sample_canonical_address)

        orchestrator = SearchOrchestrator(db_client=db_client)

        query = SearchQuery(raw_address="42 Mahatma Gandhi Road, Flat 7B, Patna, Bihar 800001")
        result = await orchestrator.resolve(query)

        assert result.resolved is not None
        assert result.resolved.sap_premise_id == sample_canonical_address.sap_premise_id
        assert result.resolved.confidence_score >= 0.92
        assert result.tiers_invoked == [0, 1]
        assert result.pincode_missing is False

        db_client.close()

    @pytest.mark.asyncio
    async def test_tier_limit_enforcement(self, sample_canonical_address: CanonicalAddress) -> None:
        """Verify tier_limit restricts cascade depth."""
        db_client = DuckDBClient(":memory:")
        await db_client.init_schema()
        await db_client.upsert_address(sample_canonical_address)

        orchestrator = SearchOrchestrator(db_client=db_client)

        query = SearchQuery(
            raw_address="42 MG Road Patna 800001",
            tier_limit=1,
        )
        result = await orchestrator.resolve(query)

        assert result.tiers_invoked == [0, 1]

        db_client.close()

    @pytest.mark.asyncio
    async def test_missing_pincode_caps_confidence_at_80(
        self, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Verify missing PIN code caps resolution confidence at 0.80."""
        db_client = DuckDBClient(":memory:")
        await db_client.init_schema()
        await db_client.upsert_address(sample_canonical_address)

        orchestrator = SearchOrchestrator(db_client=db_client)

        # Query without pincode
        query = SearchQuery(raw_address="42 Mahatma Gandhi Road, Flat 7B, Patna, Bihar")
        result = await orchestrator.resolve(query)

        assert result.pincode_missing is True
        if result.resolved:
            assert result.resolved.confidence_score <= 0.80

        db_client.close()

    @pytest.mark.asyncio
    async def test_typeahead_suggest_fast_path(
        self, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Verify suggest() executes typeahead over Tier 1 only."""
        db_client = DuckDBClient(":memory:")
        await db_client.init_schema()
        await db_client.upsert_address(sample_canonical_address)

        orchestrator = SearchOrchestrator(db_client=db_client)

        query = SearchQuery(raw_address="42 MG Road 800001", max_results=3)
        result = await orchestrator.suggest(query)

        assert result.tiers_invoked == [0, 1]
        assert len(result.candidates) >= 1
        assert result.candidates[0].sap_premise_id == sample_canonical_address.sap_premise_id

        db_client.close()
