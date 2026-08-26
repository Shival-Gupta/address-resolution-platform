# File: tests/unit/test_llm_fallback.py
"""Unit tests for Tier 3 LLM Disambiguation and fail-open degradation.

Validates structured output disambiguation, circuit breaker integration, and
graceful degradation when the LLM service times out or errors.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.core.circuit_breaker import CircuitBreaker, CircuitState
from app.engines.llm_fallback import LLMDisambiguator
from app.models.search import CandidateMatch, DisambiguationResult


class TestLLMDisambiguator:
    """Test suite for LLMDisambiguator."""

    def test_successful_disambiguation(self) -> None:
        """Verify successful LLM response selects the right candidate."""
        cb = CircuitBreaker()
        disambiguator = LLMDisambiguator(circuit_breaker=cb)

        candidates = [
            CandidateMatch(
                sap_premise_id="PR-800001-42-7A",
                canonical_address="42 MG Road, Flat 7A, Patna",
                confidence_score=0.82,
                match_tier=2,
            ),
            CandidateMatch(
                sap_premise_id="PR-800001-42-7B",
                canonical_address="42 MG Road, Flat 7B, Patna",
                confidence_score=0.81,
                match_tier=2,
            ),
        ]

        # Mock GenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.parsed = DisambiguationResult(
            selected_sap_premise_id="PR-800001-42-7B",
            confidence_score=0.96,
            rationale="Query specified Flat 7B matching candidate 2",
        )
        mock_client.models.generate_content.return_value = mock_response

        result = disambiguator.disambiguate(
            query="Flat 7B, 42 MG Road Patna",
            candidates=candidates,
            client=mock_client,
        )

        assert result.sap_premise_id == "PR-800001-42-7B"
        assert result.confidence_score == 0.96
        assert result.match_tier == 3
        assert result.confidence_degraded is False
        assert "Flat 7B" in (result.match_rationale or "")
        assert cb.state == CircuitState.CLOSED

    def test_circuit_breaker_open_fail_open_degradation(self) -> None:
        """Verify when breaker is OPEN, disambiguator fails open and returns degraded result."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        disambiguator = LLMDisambiguator(circuit_breaker=cb)

        candidates = [
            CandidateMatch(
                sap_premise_id="PR-800001-42-7A",
                canonical_address="42 MG Road, Flat 7A, Patna",
                confidence_score=0.82,
                match_tier=2,
            ),
        ]

        mock_client = MagicMock()
        result = disambiguator.disambiguate(
            query="Flat 7A 42 MG Road",
            candidates=candidates,
            client=mock_client,
        )

        # Mock client should not even be called when circuit is open
        mock_client.models.generate_content.assert_not_called()

        assert result.sap_premise_id == "PR-800001-42-7A"
        assert result.confidence_degraded is True
        assert "Circuit breaker OPEN" in (result.match_rationale or "")

    def test_llm_api_failure_fails_open_gracefully(self) -> None:
        """Verify API timeout or exception returns degraded match without raising 500."""
        cb = CircuitBreaker(failure_threshold=3)
        disambiguator = LLMDisambiguator(circuit_breaker=cb)

        candidates = [
            CandidateMatch(
                sap_premise_id="PR-800001-42-7A",
                canonical_address="42 MG Road, Flat 7A, Patna",
                confidence_score=0.80,
                match_tier=2,
            ),
        ]

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = TimeoutError("Gemini API timeout")

        result = disambiguator.disambiguate(
            query="Flat 7A 42 MG Road",
            candidates=candidates,
            client=mock_client,
        )

        assert result.sap_premise_id == "PR-800001-42-7A"
        assert result.confidence_degraded is True
        assert "LLM failure" in (result.match_rationale or "")

    def test_empty_candidates_returns_unknown(self) -> None:
        """Verify passing empty candidates returns an unknown degraded match."""
        disambiguator = LLMDisambiguator()
        result = disambiguator.disambiguate(query="Nonexistent address", candidates=[])

        assert result.sap_premise_id == "UNKNOWN"
        assert result.confidence_degraded is True
