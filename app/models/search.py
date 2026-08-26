# File: app/models/search.py
"""Search request, candidate match, and resolution response schemas.

Defines SearchQuery, CandidateMatch, SearchResult, BatchRequest, and
DisambiguationResult Pydantic models used across all 4 search tiers.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchQuery(BaseModel):
    """Inbound address resolution or typeahead query.

    Attributes:
        raw_address: Raw unparsed address input string.
        max_results: Maximum candidate matches to return (1-20).
        tier_limit: Optional tier limit to constrain execution (0, 1, 2, or 3).
        context: Optional spatial or metadata context (e.g. {"city_hint": "Patna"}).
    """

    raw_address: str = Field(..., min_length=3, max_length=500)
    max_results: int = Field(default=5, ge=1, le=20)
    tier_limit: int | None = Field(default=None, ge=0, le=3)
    context: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class CandidateMatch(BaseModel):
    """Single resolved address candidate from any engine tier.

    Attributes:
        sap_premise_id: Matched SAP premise identifier (e.g. "PR-800001-42-7B").
        canonical_address: Canonical human-readable address.
        confidence_score: Computed match confidence score between 0.0 and 1.0.
        match_tier: Engine tier that produced or finalized the match (1, 2, or 3).
        confidence_degraded: True if circuit breaker was open or degraded mode was active.
        match_rationale: Explanation from Tier 3 LLM (if invoked), otherwise None.
    """

    sap_premise_id: str
    canonical_address: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    match_tier: int = Field(..., ge=0, le=3)
    confidence_degraded: bool = False
    match_rationale: str | None = None

    model_config = ConfigDict(frozen=True)


class SearchResult(BaseModel):
    """Full API response for address search or resolution.

    Attributes:
        query: Original query string.
        candidates: List of ranked candidate matches.
        resolved: Best single match if confidence satisfies auto-resolve threshold.
        latency_ms: Total resolution latency in milliseconds.
        tiers_invoked: Sequence of engine tiers invoked (e.g. [0, 1] or [0, 1, 2, 3]).
        pincode_missing: Flag indicating whether input lacked a valid 6-digit PIN.
    """

    query: str
    candidates: list[CandidateMatch] = Field(default_factory=list)
    resolved: CandidateMatch | None = None
    latency_ms: float = 0.0
    tiers_invoked: list[int] = Field(default_factory=list)
    pincode_missing: bool = False

    model_config = ConfigDict(frozen=True)


class BatchRequest(BaseModel):
    """Inbound batch address resolution request.

    Attributes:
        addresses: List of SearchQuery objects (1-1000 items).
        callback_url: Optional webhook URL to receive completed batch results.
    """

    addresses: list[SearchQuery] = Field(..., min_length=1, max_length=1000)
    callback_url: str | None = None

    model_config = ConfigDict(frozen=True)


class DisambiguationResult(BaseModel):
    """Structured LLM response for Tier 3 address disambiguation.

    Attributes:
        selected_sap_premise_id: Selected SAP premise ID from candidates, or empty string.
        confidence_score: Disambiguation confidence score (0.0 - 1.0).
        rationale: Explanation for the chosen match.
    """

    selected_sap_premise_id: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    rationale: str

    model_config = ConfigDict(frozen=True)
