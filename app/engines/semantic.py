# File: app/engines/semantic.py
"""Tier 2 Semantic Vector Search Engine using dense embeddings and cosine similarity.

Enforces the Number-Blindness Guardrail by pre-filtering candidates on premise
number and flat number before calculating vector cosine similarities.
Provides Reciprocal Rank Fusion (RRF) to merge Tier 1 and Tier 2 rankings.
"""

from __future__ import annotations

import math
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import EmbeddingError
from app.models.address import AddressSlots
from app.models.search import CandidateMatch


def apply_number_filter(
    candidate_pool: list[dict[str, Any]], slots: AddressSlots
) -> list[dict[str, Any]]:
    """Enforce the Number-Blindness Guardrail before vector cosine computation.

    Dense bi-encoders are number-blind and cannot reliably distinguish 'Flat 7A'
    from 'Flat 7B'. This function isolates matching premise and sub-premise candidates.

    Args:
        candidate_pool: Spatial candidate pool dictionaries.
        slots: Extracted address slots containing premise_number and flat_no.

    Returns:
        list[dict[str, Any]]: Filtered candidate pool.
    """
    if not candidate_pool:
        return []

    req_premise = (slots.premise_number or "").strip().lower()
    req_flat = (slots.flat_no or "").strip().lower()

    # No numeric identifiers extracted — no filtering needed (no numbers to be blind about)
    if not req_premise and not req_flat:
        return candidate_pool

    both_provided = bool(req_premise and req_flat)

    filtered: list[dict[str, Any]] = []
    for cand in candidate_pool:
        c_premise = str(cand.get("premise_number") or "").strip().lower()
        c_flat = str(cand.get("flat_no") or "").strip().lower()

        premise_match = not req_premise or (c_premise == req_premise)
        flat_match = not req_flat or (c_flat == req_flat)

        if premise_match and flat_match:
            filtered.append(cand)

    if filtered:
        return filtered

    # ARCHITECTURAL INVARIANT: If BOTH premise_number AND flat_no were extracted but
    # no candidates matched, we must NOT fall back to the full pool.
    # Returning the full pool would silently re-enable number-blindness for the most
    # dangerous case (distinguishing Flat 7A from Flat 7B in the same building).
    # Return empty list — the orchestrator will escalate to Tier 3 LLM for resolution.
    if both_provided:
        return []

    # Only ONE of premise/flat was provided and yielded no match.
    # Lenient fallback: filter only by the one that was provided, ignoring the other.
    lenient: list[dict[str, Any]] = []
    for cand in candidate_pool:
        c_premise = str(cand.get("premise_number") or "").strip().lower()
        c_flat = str(cand.get("flat_no") or "").strip().lower()
        if (req_premise and c_premise == req_premise) or (req_flat and c_flat == req_flat):
            lenient.append(cand)

    return lenient if lenient else candidate_pool


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two float vectors.

    Args:
        vec_a: First dense float vector.
        vec_b: Second dense float vector.

    Returns:
        float: Cosine similarity in range -1.0 to 1.0 (clamped to 0.0 - 1.0).
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    sim = dot_product / (norm_a * norm_b)
    return max(0.0, min(1.0, float(sim)))


def generate_embedding(text: str, client: Any = None) -> list[float]:
    """Generate dense 768-dimensional embedding vector for input text.

    Args:
        text: Address text to embed.
        client: Optional Google GenAI client instance.

    Returns:
        list[float]: 768-dimensional float embedding.

    Raises:
        EmbeddingError: If API call fails.
    """
    if not text or not text.strip():
        return [0.0] * 768

    settings = get_settings()

    # If no client or API key, return deterministic mock embedding for tests
    if not client and not settings.GEMINI_API_KEY:
        # Generate deterministic synthetic vector based on character hashes
        vec = [0.0] * 768
        for i, char in enumerate(text.lower()):
            idx = (ord(char) * (i + 1)) % 768
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    try:
        if not client:
            from google import genai

            client = genai.Client(api_key=settings.GEMINI_API_KEY)

        response = client.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=text,
        )
        embedding_val: list[float] = list(response.embeddings[0].values)
        return embedding_val
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingError(f"Embedding generation failed: {exc}") from exc


def batch_embed(texts: list[str], client: Any = None, batch_size: int = 64) -> list[list[float]]:
    """Batch embed multiple address strings in chunks of max 64 items.

    Args:
        texts: List of address strings.
        client: Optional Google GenAI client instance.
        batch_size: Maximum batch size per API call (capped at 64).

    Returns:
        list[list[float]]: List of 768-dimensional dense vectors.
    """
    if not texts:
        return []

    settings = get_settings()
    eff_batch_size = min(batch_size, 64)
    all_embeddings: list[list[float]] = []

    # If no client or API key, use fallback generator
    if not client and not settings.GEMINI_API_KEY:
        return [generate_embedding(t) for t in texts]

    try:
        if not client:
            from google import genai

            client = genai.Client(api_key=settings.GEMINI_API_KEY)

        for i in range(0, len(texts), eff_batch_size):
            chunk = texts[i : i + eff_batch_size]
            response = client.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=chunk,
            )
            for emb in response.embeddings:
                all_embeddings.append(list(emb.values))
        return all_embeddings
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingError(f"Batch embedding failed: {exc}") from exc


def reciprocal_rank_fusion(
    t1_matches: list[CandidateMatch],
    t2_matches: list[CandidateMatch],
    k: int = 60,
) -> list[CandidateMatch]:
    """Fuse Tier 1 and Tier 2 candidate rankings using Reciprocal Rank Fusion (RRF).

    Formula: rrf_score = 1/(k + rank_t1) + 1/(k + rank_t2)

    Args:
        t1_matches: Ranked CandidateMatch list from Tier 1.
        t2_matches: Ranked CandidateMatch list from Tier 2.
        k: Smoothing constant (default 60).

    Returns:
        list[CandidateMatch]: Fused candidates sorted by combined RRF score.
    """
    scores: dict[str, float] = {}
    candidate_map: dict[str, CandidateMatch] = {}

    for rank, m in enumerate(t1_matches):
        scores[m.sap_premise_id] = scores.get(m.sap_premise_id, 0.0) + 1.0 / (k + rank + 1)
        candidate_map[m.sap_premise_id] = m

    for rank, m in enumerate(t2_matches):
        scores[m.sap_premise_id] = scores.get(m.sap_premise_id, 0.0) + 1.0 / (k + rank + 1)
        if m.sap_premise_id not in candidate_map:
            candidate_map[m.sap_premise_id] = m

    # Max possible RRF score with 2 tiers at rank 1 is 2 / (k + 1)
    max_possible = 2.0 / (k + 1.0)

    fused_results: list[CandidateMatch] = []
    for sap_id, raw_score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        base_match = candidate_map[sap_id]
        normalized_conf = min(1.0, round(raw_score / max_possible, 4))
        fused_results.append(
            CandidateMatch(
                sap_premise_id=base_match.sap_premise_id,
                canonical_address=base_match.canonical_address,
                confidence_score=normalized_conf,
                match_tier=2,
                confidence_degraded=False,
                match_rationale="RRF Tier 1 + Tier 2 fused ranking",
            )
        )

    return fused_results


def search(
    slots: AddressSlots,
    candidate_pool: list[dict[str, Any]],
    query_embedding: list[float] | None = None,
    top_k: int = 5,
) -> list[CandidateMatch]:
    """Execute Tier 2 dense vector semantic matching over candidate pool.

    Strictly applies Number-Blindness Guardrail before computing cosine similarities.

    Args:
        slots: Extracted address slots.
        candidate_pool: Spatial candidate pool dictionaries with embeddings.
        query_embedding: Pre-computed query embedding vector or None.
        top_k: Maximum candidate matches to return.

    Returns:
        list[CandidateMatch]: Scored candidate matches from Tier 2.
    """
    if not candidate_pool:
        return []

    # Step 1: HARD GUARDRAIL - Apply Number Filter
    filtered_pool = apply_number_filter(candidate_pool, slots)

    # Step 2: Ensure query embedding exists
    q_vec = query_embedding or generate_embedding(" ".join(slots.normalized_tokens))

    scored_candidates: list[tuple[float, dict[str, Any]]] = []
    for cand in filtered_pool:
        c_emb = cand.get("embedding")
        if not c_emb:
            c_str = str(cand.get("normalized_str") or cand.get("full_address", ""))
            c_emb = generate_embedding(c_str)

        sim = cosine_similarity(q_vec, c_emb)
        scored_candidates.append((sim, cand))

    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    results: list[CandidateMatch] = []
    for sim, cand in scored_candidates[:top_k]:
        results.append(
            CandidateMatch(
                sap_premise_id=str(cand["sap_premise_id"]),
                canonical_address=str(cand["full_address"]),
                confidence_score=round(sim, 4),
                match_tier=2,
                confidence_degraded=False,
                match_rationale=None,
            )
        )

    return results
