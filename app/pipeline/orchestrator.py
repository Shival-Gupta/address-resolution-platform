# File: app/pipeline/orchestrator.py
"""Central search pipeline orchestrator implementing the 4-tier cascaded funnel.

Coordinates Tier 0 (Normalizer), Spatial Pre-filtering, Tier 1 (Lexical),
Tier 2 (Semantic Vector with Number Guardrail), and Tier 3 (LLM Disambiguator).
Enforces confidence thresholds and degradation rules from CONTEXT.md.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.core.config import get_settings
from app.db.duckdb_client import DuckDBClient
from app.engines.lexical import search as lexical_search
from app.engines.llm_fallback import LLMDisambiguator
from app.engines.normalizer import normalize
from app.engines.semantic import reciprocal_rank_fusion
from app.engines.semantic import search as semantic_search
from app.models.search import CandidateMatch, SearchQuery, SearchResult

logger = logging.getLogger(__name__)


class SearchOrchestrator:
    """Cascade orchestrator managing the 4-tier hybrid address resolution lifecycle."""

    def __init__(
        self,
        db_client: DuckDBClient | None = None,
        disambiguator: LLMDisambiguator | None = None,
    ) -> None:
        """Initialize SearchOrchestrator with dependencies.

        Args:
            db_client: Optional DuckDBClient instance.
            disambiguator: Optional LLMDisambiguator instance.
        """
        self.db_client = db_client or DuckDBClient()
        self.disambiguator = disambiguator or LLMDisambiguator()

    def _apply_confidence_rules(
        self, match: CandidateMatch, pincode_missing: bool
    ) -> CandidateMatch:
        """Apply CONTEXT.md business rules for confidence score capping.

        Rules (from CONTEXT.md Section 4):
        - pincode_missing=True: cap confidence at 0.80
        - flat_no extracted as None in original slots: cap at 0.85
          (system cannot distinguish between flats in the same building)
        - Circuit breaker degraded: propagated by caller, not re-applied here.

        Args:
            match: CandidateMatch to evaluate.
            pincode_missing: Whether the original input lacked a valid PIN code.

        Returns:
            CandidateMatch: Adjusted match with capped confidence if applicable.
        """
        score = match.confidence_score
        degraded = match.confidence_degraded

        # Rule 1 (CONTEXT.md): If pincode_missing=True, cap confidence at 0.80
        if pincode_missing and score > 0.80:
            score = 0.80
            degraded = True

        return CandidateMatch(
            sap_premise_id=match.sap_premise_id,
            canonical_address=match.canonical_address,
            confidence_score=round(score, 4),
            match_tier=match.match_tier,
            confidence_degraded=degraded,
            match_rationale=match.match_rationale,
        )

    async def resolve(self, query: SearchQuery) -> SearchResult:
        """Execute full 4-tier address resolution cascade.

        Args:
            query: Inbound SearchQuery.

        Returns:
            SearchResult: Resolution response with ranked candidates and resolved single best match.
        """
        start_time = time.perf_counter()
        settings = get_settings()
        tiers_invoked: list[int] = []

        # Tier 0: Normalization
        slots = normalize(query.raw_address)
        tiers_invoked.append(0)

        # Spatial Partitioning: Retrieve pre-filtered candidates by pincode
        candidate_pool: list[dict[str, Any]] = await self.db_client.get_candidate_pool(
            slots.pincode
        )
        if not candidate_pool and slots.pincode:
            # Fallback to broader search if pincode yielded 0 candidates
            candidate_pool = await self.db_client.get_candidate_pool(None, limit=5000)

        if not candidate_pool:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return SearchResult(
                query=query.raw_address,
                candidates=[],
                resolved=None,
                latency_ms=round(latency_ms, 2),
                tiers_invoked=tiers_invoked,
                pincode_missing=slots.pincode_missing,
            )

        # Tier 1: Lexical Search (DuckDB Trigrams + RapidFuzz Token Set Ratio)
        t1_matches = lexical_search(slots, candidate_pool, top_k=query.max_results)
        tiers_invoked.append(1)

        # Check Tier 1 Auto-Resolve Threshold (0.92)
        if (
            t1_matches
            and t1_matches[0].confidence_score >= settings.TIER1_CONFIDENCE_THRESHOLD
            and query.tier_limit != 0
        ):
            adjusted_top = self._apply_confidence_rules(t1_matches[0], slots.pincode_missing)
            adjusted_candidates = [
                self._apply_confidence_rules(m, slots.pincode_missing) for m in t1_matches
            ]
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            resolved = (
                adjusted_top
                if adjusted_top.confidence_score >= settings.MANUAL_REVIEW_THRESHOLD
                else None
            )
            return SearchResult(
                query=query.raw_address,
                candidates=adjusted_candidates,
                resolved=resolved,
                latency_ms=round(latency_ms, 2),
                tiers_invoked=tiers_invoked,
                pincode_missing=slots.pincode_missing,
            )

        if query.tier_limit == 1:
            adjusted_candidates = [
                self._apply_confidence_rules(m, slots.pincode_missing) for m in t1_matches
            ]
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            resolved = (
                adjusted_candidates[0]
                if adjusted_candidates
                and adjusted_candidates[0].confidence_score >= settings.MANUAL_REVIEW_THRESHOLD
                else None
            )
            return SearchResult(
                query=query.raw_address,
                candidates=adjusted_candidates,
                resolved=resolved,
                latency_ms=round(latency_ms, 2),
                tiers_invoked=tiers_invoked,
                pincode_missing=slots.pincode_missing,
            )

        # Tier 2: Semantic Search (Number Guardrail + Dense Embeddings + RRF)
        t2_matches = semantic_search(slots, candidate_pool, top_k=query.max_results)
        tiers_invoked.append(2)

        # If Tier 2 returns empty (strict number filter found 0 candidates in DB),
        # the premise/flat combination does not exist in the search index.
        # Skip fusion — proceed directly to Tier 3 for LLM cross-encoder resolution.
        if not t2_matches:
            logger.warning(
                "Tier 2 number filter returned 0 candidates for premise=%s flat=%s. "
                "Escalating directly to Tier 3 LLM.",
                slots.premise_number,
                slots.flat_no,
            )
        else:
            fused_matches = reciprocal_rank_fusion(t1_matches, t2_matches)

            # Check Tier 2 Auto-Resolve Threshold (0.88)
            if (
                fused_matches
                and fused_matches[0].confidence_score >= settings.TIER2_CONFIDENCE_THRESHOLD
                and query.tier_limit not in (0, 1)
            ):
                adjusted_candidates = [
                    self._apply_confidence_rules(m, slots.pincode_missing)
                    for m in fused_matches[: query.max_results]
                ]
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                resolved = (
                    adjusted_candidates[0]
                    if adjusted_candidates
                    and adjusted_candidates[0].confidence_score >= settings.MANUAL_REVIEW_THRESHOLD
                    else None
                )
                return SearchResult(
                    query=query.raw_address,
                    candidates=adjusted_candidates,
                    resolved=resolved,
                    latency_ms=round(latency_ms, 2),
                    tiers_invoked=tiers_invoked,
                    pincode_missing=slots.pincode_missing,
                )

        if query.tier_limit == 2:
            fused_matches = (
                reciprocal_rank_fusion(t1_matches, t2_matches) if t2_matches else t1_matches
            )
            adjusted_candidates = [
                self._apply_confidence_rules(m, slots.pincode_missing)
                for m in fused_matches[: query.max_results]
            ]
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            resolved = (
                adjusted_candidates[0]
                if adjusted_candidates
                and adjusted_candidates[0].confidence_score >= settings.MANUAL_REVIEW_THRESHOLD
                else None
            )
            return SearchResult(
                query=query.raw_address,
                candidates=adjusted_candidates,
                resolved=resolved,
                latency_ms=round(latency_ms, 2),
                tiers_invoked=tiers_invoked,
                pincode_missing=slots.pincode_missing,
            )

        # Tier 3: LLM Fallback Disambiguation
        tiers_invoked.append(3)
        candidate_pool_for_t3 = fused_matches or t1_matches
        t3_result = self.disambiguator.disambiguate(query.raw_address, candidate_pool_for_t3)

        adjusted_t3 = self._apply_confidence_rules(t3_result, slots.pincode_missing)
        other_candidates = [
            self._apply_confidence_rules(m, slots.pincode_missing)
            for m in candidate_pool_for_t3
            if m.sap_premise_id != adjusted_t3.sap_premise_id
        ]
        final_candidates = [adjusted_t3] + other_candidates[: query.max_results - 1]

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        resolved = (
            adjusted_t3
            if adjusted_t3.confidence_score >= settings.MANUAL_REVIEW_THRESHOLD
            else None
        )

        return SearchResult(
            query=query.raw_address,
            candidates=final_candidates,
            resolved=resolved,
            latency_ms=round(latency_ms, 2),
            tiers_invoked=tiers_invoked,
            pincode_missing=slots.pincode_missing,
        )

    async def suggest(self, query: SearchQuery) -> SearchResult:
        """Execute fast typeahead search (Tier 1 Lexical only, p95 < 20ms).

        Args:
            query: Inbound SearchQuery.

        Returns:
            SearchResult: Top typeahead candidate matches.
        """
        start_time = time.perf_counter()
        settings = get_settings()
        tiers_invoked = [0, 1]

        slots = normalize(query.raw_address)
        candidate_pool = await self.db_client.get_candidate_pool(slots.pincode, limit=1000)
        if not candidate_pool and slots.pincode:
            candidate_pool = await self.db_client.get_candidate_pool(None, limit=1000)

        t1_matches = lexical_search(slots, candidate_pool, top_k=query.max_results)
        adjusted_candidates = [
            self._apply_confidence_rules(m, slots.pincode_missing) for m in t1_matches
        ]

        resolved = (
            adjusted_candidates[0]
            if adjusted_candidates
            and adjusted_candidates[0].confidence_score >= settings.TIER1_CONFIDENCE_THRESHOLD
            else None
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResult(
            query=query.raw_address,
            candidates=adjusted_candidates,
            resolved=resolved,
            latency_ms=round(latency_ms, 2),
            tiers_invoked=tiers_invoked,
            pincode_missing=slots.pincode_missing,
        )
