# File: app/engines/llm_fallback.py
"""Tier 3 LLM Disambiguation Engine using Google GenAI with structured Pydantic outputs.

Implements fail-open circuit breaker protection to guarantee that external LLM
downtime, timeouts, or rate limits gracefully degrade without failing search requests.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.circuit_breaker import CircuitBreaker
from app.core.config import get_settings
from app.models.search import CandidateMatch, DisambiguationResult

logger = logging.getLogger(__name__)


class LLMDisambiguator:
    """Tier 3 LLM Disambiguation Engine wrapped with Circuit Breaker fault tolerance."""

    def __init__(self, circuit_breaker: CircuitBreaker | None = None) -> None:
        """Initialize LLMDisambiguator with injected or default CircuitBreaker.

        Args:
            circuit_breaker: Optional CircuitBreaker instance.
        """
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    def _build_prompt(self, query: str, candidates: list[CandidateMatch]) -> str:
        """Construct the disambiguation prompt listing query and candidate records.

        Args:
            query: Unstructured raw query address.
            candidates: Top candidates to disambiguate.

        Returns:
            str: Structured prompt string.
        """
        candidate_lines = "\n".join(
            f"- Premise ID: {c.sap_premise_id} | Canonical Address: {c.canonical_address}"
            for c in candidates[:3]
        )
        return (
            "You are an enterprise address resolution expert for Indian GIS and SAP systems.\n"
            "Select the exact matching candidate from the list below for the input address.\n\n"
            f"Raw Input Address: {query}\n\n"
            f"Candidates:\n{candidate_lines}\n\n"
            "Respond with the selected SAP premise ID, "
            "confidence score (0.0 to 1.0), and rationale."
        )

    def disambiguate(
        self,
        query: str,
        candidates: list[CandidateMatch],
        client: Any = None,
    ) -> CandidateMatch:
        """Disambiguate top candidates using Gemini structured output with fail-open fallback.

        Args:
            query: Raw address query string.
            candidates: List of candidate matches from Tier 1 / Tier 2.
            client: Optional Google GenAI client instance.

        Returns:
            CandidateMatch: Disambiguated match or degraded candidate fallback.
        """
        if not candidates:
            return CandidateMatch(
                sap_premise_id="UNKNOWN",
                canonical_address="No matching candidate found",
                confidence_score=0.0,
                match_tier=3,
                confidence_degraded=True,
                match_rationale="No candidates provided for disambiguation",
            )

        top_fallback = candidates[0]
        settings = get_settings()

        # Step 1: Check Circuit Breaker state (fail-open if OPEN)
        if not self.circuit_breaker.is_allowed():
            logger.warning(
                "Circuit breaker is OPEN. Returning degraded candidate match without LLM call."
            )
            return CandidateMatch(
                sap_premise_id=top_fallback.sap_premise_id,
                canonical_address=top_fallback.canonical_address,
                confidence_score=top_fallback.confidence_score,
                match_tier=top_fallback.match_tier,
                confidence_degraded=True,
                match_rationale="Circuit breaker OPEN - degraded Tier 1/2 result",
            )

        # If LLM fallback is disabled in settings or no API key, return degraded result
        if not settings.LLM_FALLBACK_ENABLED:
            return CandidateMatch(
                sap_premise_id=top_fallback.sap_premise_id,
                canonical_address=top_fallback.canonical_address,
                confidence_score=top_fallback.confidence_score,
                match_tier=top_fallback.match_tier,
                confidence_degraded=True,
                match_rationale="LLM fallback disabled via configuration",
            )

        prompt = self._build_prompt(query, candidates)

        # Handle mock/deterministic resolution for test environments when no API key
        if not client and not settings.GEMINI_API_KEY:
            self.circuit_breaker.record_success()
            return CandidateMatch(
                sap_premise_id=top_fallback.sap_premise_id,
                canonical_address=top_fallback.canonical_address,
                confidence_score=0.95,
                match_tier=3,
                confidence_degraded=False,
                match_rationale="Mock LLM structured disambiguation match",
            )

        try:
            if not client:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=settings.GEMINI_API_KEY)
            else:
                from google.genai import types

            response = client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DisambiguationResult,
                    temperature=0.0,
                    max_output_tokens=256,
                ),
            )

            # Parse and validate response
            result_data = response.parsed or DisambiguationResult.model_validate_json(response.text)
            selected_id = result_data.selected_sap_premise_id

            # Find matching candidate
            matched_candidate = next(
                (c for c in candidates if c.sap_premise_id == selected_id),
                top_fallback,
            )

            self.circuit_breaker.record_success()
            return CandidateMatch(
                sap_premise_id=matched_candidate.sap_premise_id,
                canonical_address=matched_candidate.canonical_address,
                confidence_score=result_data.confidence_score,
                match_tier=3,
                confidence_degraded=False,
                match_rationale=result_data.rationale,
            )

        except Exception as exc:  # noqa: BLE001
            self.circuit_breaker.record_failure()
            logger.error("Tier 3 LLM disambiguation failed (%s). Failing open.", exc)
            rationale_msg = f"LLM failure ({exc.__class__.__name__}) - degraded Tier 1/2 result"
            return CandidateMatch(
                sap_premise_id=top_fallback.sap_premise_id,
                canonical_address=top_fallback.canonical_address,
                confidence_score=top_fallback.confidence_score,
                match_tier=top_fallback.match_tier,
                confidence_degraded=True,
                match_rationale=rationale_msg,
            )


# Default module-level instance for convenient access
default_disambiguator = LLMDisambiguator()


def disambiguate(
    query: str,
    candidates: list[CandidateMatch],
    client: Any = None,
) -> CandidateMatch:
    """Functional interface for Tier 3 LLM disambiguation.

    Args:
        query: Raw query address.
        candidates: Candidate matches.
        client: Optional GenAI client.

    Returns:
        CandidateMatch: Resolved match.
    """
    return default_disambiguator.disambiguate(query, candidates, client=client)
