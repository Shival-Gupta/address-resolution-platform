# File: tests/unit/test_lexical.py
"""Unit tests for Tier 1 Lexical Search Engine.

Validates RapidFuzz token set ratio order-invariance, trigram similarity,
weighted candidate ranking, and search execution over spatial candidate pools.
"""

from __future__ import annotations

from typing import Any

from app.engines.lexical import (
    compute_token_set_ratio,
    compute_trigram_similarity,
    search,
)
from app.models.address import AddressSlots


class TestLexicalMetrics:
    """Test suite for lexical scoring functions."""

    def test_token_set_ratio_order_invariance(self) -> None:
        """Verify Token Set Ratio is order-invariant for shuffled address parts."""
        a = "42 mahatma gandhi road flat 7b patna bihar 800001"
        b = "flat 7b 42 mahatma gandhi road bihar patna 800001"
        score = compute_token_set_ratio(a, b)
        assert score >= 0.95

    def test_token_set_ratio_typo_tolerance(self) -> None:
        """Verify Token Set Ratio tolerates minor typos."""
        a = "mahatama gandhi road"
        b = "mahatma gandhi road"
        score = compute_token_set_ratio(a, b)
        assert score >= 0.88

    def test_trigram_similarity_identical_strings(self) -> None:
        """Verify trigram similarity equals 1.0 for identical strings."""
        s = "mahatma gandhi road"
        assert compute_trigram_similarity(s, s) == 1.0

    def test_trigram_similarity_disjoint_strings(self) -> None:
        """Verify trigram similarity is low/zero for completely disjoint strings."""
        assert compute_trigram_similarity("abcdef", "uvwxyz") == 0.0


class TestLexicalSearch:
    """Test suite for Tier 1 search execution."""

    def test_search_ranks_correct_candidate_top(self, sample_slots: AddressSlots) -> None:
        """Verify lexical search ranks the best matching candidate first."""
        candidate_pool: list[dict[str, Any]] = [
            {
                "sap_premise_id": "PR-800001-42-7B",
                "full_address": "42 Mahatma Gandhi Road, Flat 7B, Patna, Bihar 800001, India",
                "normalized_str": "42 7b bihar flat gandhi india mahatma patna road",
            },
            {
                "sap_premise_id": "PR-800001-100-1A",
                "full_address": "100 Boring Road, Flat 1A, Patna, Bihar 800001, India",
                "normalized_str": "100 1a bihar boring flat india patna road",
            },
            {
                "sap_premise_id": "PR-800001-50-2C",
                "full_address": "50 Frazer Road, Flat 2C, Patna, Bihar 800001, India",
                "normalized_str": "50 2c bihar flat frazer india patna road",
            },
        ]

        matches = search(sample_slots, candidate_pool, top_k=2)

        assert len(matches) == 2
        top_match = matches[0]
        assert top_match.sap_premise_id == "PR-800001-42-7B"
        assert top_match.confidence_score >= 0.90
        assert top_match.match_tier == 1
        assert top_match.confidence_degraded is False

    def test_search_empty_pool_returns_empty_list(self, sample_slots: AddressSlots) -> None:
        """Verify searching an empty candidate pool returns an empty list."""
        matches = search(sample_slots, [], top_k=5)
        assert matches == []
