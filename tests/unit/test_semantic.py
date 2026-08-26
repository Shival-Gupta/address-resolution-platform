# File: tests/unit/test_semantic.py
"""Unit tests for Tier 2 Semantic Vector Search Engine.

Validates cosine similarity calculation, embedding batching, Reciprocal Rank Fusion,
and the Number-Blindness Guardrail (strict isolation between Flat 7A and Flat 7B).
"""

from __future__ import annotations

from typing import Any

from app.engines.semantic import (
    apply_number_filter,
    batch_embed,
    cosine_similarity,
    generate_embedding,
    reciprocal_rank_fusion,
    search,
)
from app.models.address import AddressSlots
from app.models.search import CandidateMatch


class TestNumberBlindnessGuardrail:
    """Validate Number-Blindness guardrail filtering before vector calculations."""

    def test_apply_number_filter_isolates_flat_units(self) -> None:
        """Verify candidate pool is strictly filtered to matching flat and premise."""
        candidate_pool: list[dict[str, Any]] = [
            {
                "sap_premise_id": "PR-800001-42-7A",
                "premise_number": "42",
                "flat_no": "7a",
                "full_address": "42 MG Road, Flat 7A, Patna",
            },
            {
                "sap_premise_id": "PR-800001-42-7B",
                "premise_number": "42",
                "flat_no": "7b",
                "full_address": "42 MG Road, Flat 7B, Patna",
            },
            {
                "sap_premise_id": "PR-800001-42-7C",
                "premise_number": "42",
                "flat_no": "7c",
                "full_address": "42 MG Road, Flat 7C, Patna",
            },
        ]

        # Search for Flat 7B
        slots_7b = AddressSlots(
            raw_input="42 MG Road Flat 7B",
            premise_number="42",
            flat_no="7b",
            pincode="800001",
        )

        filtered = apply_number_filter(candidate_pool, slots_7b)
        assert len(filtered) == 1
        assert filtered[0]["sap_premise_id"] == "PR-800001-42-7B"

        # Search for Flat 7A
        slots_7a = AddressSlots(
            raw_input="42 MG Road Flat 7A",
            premise_number="42",
            flat_no="7a",
            pincode="800001",
        )

        filtered_7a = apply_number_filter(candidate_pool, slots_7a)
        assert len(filtered_7a) == 1
        assert filtered_7a[0]["sap_premise_id"] == "PR-800001-42-7A"


class TestVectorMathAndEmbeddings:
    """Validate cosine similarity and batch embedding generation."""

    def test_cosine_similarity_identical_vectors(self) -> None:
        """Verify cosine similarity of identical vectors is 1.0."""
        vec = [0.5, 0.5, 0.5, 0.5]
        assert abs(cosine_similarity(vec, vec) - 1.0) < 1e-5

    def test_cosine_similarity_orthogonal_vectors(self) -> None:
        """Verify cosine similarity of orthogonal vectors is 0.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        assert cosine_similarity(vec_a, vec_b) == 0.0

    def test_deterministic_embedding_generation(self) -> None:
        """Verify deterministic fallback embedding produces 768-dim normalized vector."""
        emb1 = generate_embedding("42 Mahatma Gandhi Road Patna")
        emb2 = generate_embedding("42 Mahatma Gandhi Road Patna")

        assert len(emb1) == 768
        assert emb1 == emb2
        assert abs(cosine_similarity(emb1, emb2) - 1.0) < 1e-5

    def test_batch_embed_chunks_correctly(self) -> None:
        """Verify batch embedding generates vectors for all input texts."""
        texts = [f"Address line {i} Patna 800001" for i in range(10)]
        embeddings = batch_embed(texts, batch_size=4)

        assert len(embeddings) == 10
        assert all(len(emb) == 768 for emb in embeddings)


class TestReciprocalRankFusion:
    """Validate RRF merging of Tier 1 and Tier 2 candidate rankings."""

    def test_rrf_combines_and_boosts_top_ranked_in_both(self) -> None:
        """Verify candidate ranked #1 in both T1 and T2 is ranked #1 in fused output."""
        t1 = [
            CandidateMatch(
                sap_premise_id="PR-1",
                canonical_address="Address 1",
                confidence_score=0.92,
                match_tier=1,
            ),
            CandidateMatch(
                sap_premise_id="PR-2",
                canonical_address="Address 2",
                confidence_score=0.85,
                match_tier=1,
            ),
        ]

        t2 = [
            CandidateMatch(
                sap_premise_id="PR-1",
                canonical_address="Address 1",
                confidence_score=0.90,
                match_tier=2,
            ),
            CandidateMatch(
                sap_premise_id="PR-3",
                canonical_address="Address 3",
                confidence_score=0.88,
                match_tier=2,
            ),
        ]

        fused = reciprocal_rank_fusion(t1, t2, k=60)

        assert len(fused) == 3
        assert fused[0].sap_premise_id == "PR-1"
        assert fused[0].confidence_score == 1.0
        assert fused[0].match_tier == 2


class TestSemanticSearch:
    """Validate Tier 2 search execution."""

    def test_semantic_search_with_number_guardrail(self) -> None:
        """Verify semantic search applies number filter and scores top candidate."""
        emb_7a = generate_embedding("42 Mahatma Gandhi Road Flat 7A Patna")
        emb_7b = generate_embedding("42 Mahatma Gandhi Road Flat 7B Patna")

        candidate_pool: list[dict[str, Any]] = [
            {
                "sap_premise_id": "PR-800001-42-7A",
                "premise_number": "42",
                "flat_no": "7a",
                "full_address": "42 Mahatma Gandhi Road, Flat 7A, Patna",
                "embedding": emb_7a,
            },
            {
                "sap_premise_id": "PR-800001-42-7B",
                "premise_number": "42",
                "flat_no": "7b",
                "full_address": "42 Mahatma Gandhi Road, Flat 7B, Patna",
                "embedding": emb_7b,
            },
        ]

        slots_7b = AddressSlots(
            raw_input="42 MG Rd Flat 7B Patna",
            premise_number="42",
            flat_no="7b",
            normalized_tokens=["42", "7b", "gandhi", "mahatma", "patna", "road"],
        )

        matches = search(slots_7b, candidate_pool, top_k=2)

        assert len(matches) == 1
        assert matches[0].sap_premise_id == "PR-800001-42-7B"
        assert matches[0].match_tier == 2
