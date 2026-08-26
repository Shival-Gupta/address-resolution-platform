# File: app/engines/lexical.py
"""Tier 1 Lexical Search Engine using DuckDB trigrams and RapidFuzz Token Set Ratio.

Provides sub-8ms order-invariant lexical matching combining character 3-gram
similarity with RapidFuzz token set ratio over pre-filtered spatial candidate pools.
"""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from app.models.address import AddressSlots
from app.models.search import CandidateMatch


def compute_token_set_ratio(query_str: str, candidate_str: str) -> float:
    """Compute normalized RapidFuzz token set ratio between two address strings.

    Args:
        query_str: Normalized query token string.
        candidate_str: Normalized candidate address string.

    Returns:
        float: Similarity score between 0.0 and 1.0.
    """
    if not query_str or not candidate_str:
        return 0.0
    score = fuzz.token_set_ratio(query_str, candidate_str)
    return float(score) / 100.0


def compute_trigram_similarity(str_a: str, str_b: str) -> float:
    """Compute character 3-gram Jaccard similarity between two strings.

    Args:
        str_a: First comparison string.
        str_b: Second comparison string.

    Returns:
        float: Trigram Jaccard coefficient between 0.0 and 1.0.
    """
    if not str_a or not str_b:
        return 0.0

    # Generate 3-grams
    trigrams_a = {str_a[i : i + 3] for i in range(max(0, len(str_a) - 2))}
    trigrams_b = {str_b[i : i + 3] for i in range(max(0, len(str_b) - 2))}

    if not trigrams_a or not trigrams_b:
        return 1.0 if str_a.strip().lower() == str_b.strip().lower() else 0.0

    intersection = len(trigrams_a & trigrams_b)
    union = len(trigrams_a | trigrams_b)

    return float(intersection) / float(union) if union > 0 else 0.0


def search(
    slots: AddressSlots, candidate_pool: list[dict[str, Any]], top_k: int = 5
) -> list[CandidateMatch]:
    """Execute Tier 1 lexical matching over candidate pool.

    Combines Token Set Ratio (60% weight) and Trigram Similarity (40% weight).

    Args:
        slots: Extracted address slots from Tier 0 normalizer.
        candidate_pool: Pre-filtered list of candidate address dictionaries.
        top_k: Maximum candidate matches to return.

    Returns:
        list[CandidateMatch]: Ranked list of candidate matches scored by lexical similarity.
    """
    if not candidate_pool:
        return []

    query_str = " ".join(slots.normalized_tokens)
    scored_candidates: list[tuple[float, dict[str, Any]]] = []

    for cand in candidate_pool:
        cand_str = str(cand.get("normalized_str") or cand.get("full_address", ""))

        ts_score = compute_token_set_ratio(query_str, cand_str)
        tri_score = compute_trigram_similarity(query_str, cand_str)

        # Weighted combination: 0.6 * token_set + 0.4 * trigram
        combined_score = round(0.6 * ts_score + 0.4 * tri_score, 4)
        scored_candidates.append((combined_score, cand))

    # Sort descending by score
    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    results: list[CandidateMatch] = []
    for score, cand in scored_candidates[:top_k]:
        results.append(
            CandidateMatch(
                sap_premise_id=str(cand["sap_premise_id"]),
                canonical_address=str(cand["full_address"]),
                confidence_score=min(1.0, max(0.0, score)),
                match_tier=1,
                confidence_degraded=False,
                match_rationale=None,
            )
        )

    return results
