# File: tests/unit/test_models.py
"""Unit tests for Pydantic V2 models across address and search modules.

Validates model creation, schema immutability (frozen=True), field validations,
serialization/deserialization, and edge cases.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.address import AddressSlots, CanonicalAddress
from app.models.search import BatchRequest, CandidateMatch, SearchQuery, SearchResult


class TestAddressSlots:
    """Test suite for AddressSlots model."""

    def test_valid_address_slots(self, sample_slots: AddressSlots) -> None:
        """Test creating a valid AddressSlots instance."""
        assert sample_slots.raw_input.startswith("Flat 7B")
        assert sample_slots.pincode == "800001"
        assert sample_slots.pincode_missing is False
        assert sample_slots.premise_number == "42"
        assert sample_slots.flat_no == "7b"
        assert sample_slots.country == "india"
        assert len(sample_slots.normalized_tokens) > 0

    def test_address_slots_defaults(self) -> None:
        """Test default values for optional fields."""
        slots = AddressSlots(raw_input="Sample Address")
        assert slots.raw_input == "Sample Address"
        assert slots.pincode is None
        assert slots.pincode_missing is False
        assert slots.country == "India"
        assert slots.normalized_tokens == []

    def test_address_slots_immutability(self, sample_slots: AddressSlots) -> None:
        """Test that AddressSlots is frozen and immutable."""
        with pytest.raises(ValidationError):
            sample_slots.pincode = "110001"  # type: ignore[misc]

    def test_pydantic_v2_serialization(self, sample_slots: AddressSlots) -> None:
        """Test serialization using Pydantic V2 model_dump and model_validate."""
        data = sample_slots.model_dump()
        assert isinstance(data, dict)
        assert data["pincode"] == "800001"

        reconstructed = AddressSlots.model_validate(data)
        assert reconstructed == sample_slots


class TestCanonicalAddress:
    """Test suite for CanonicalAddress model."""

    def test_valid_canonical_address(self, sample_canonical_address: CanonicalAddress) -> None:
        """Test creating a valid CanonicalAddress instance."""
        assert sample_canonical_address.sap_premise_id == "PR-800001-42-7B"
        assert sample_canonical_address.source_db == "SAP_HANA"
        assert sample_canonical_address.slots.premise_number == "42"
        assert sample_canonical_address.created_at is not None
        assert sample_canonical_address.updated_at is not None

    def test_canonical_address_immutability(
        self, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Test that CanonicalAddress is frozen and immutable."""
        with pytest.raises(ValidationError):
            sample_canonical_address.sap_premise_id = "PR-NEW"  # type: ignore[misc]

    def test_canonical_address_serialization(
        self, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Test Pydantic V2 model_dump and model_validate roundtrip."""
        data = sample_canonical_address.model_dump()
        assert data["sap_premise_id"] == "PR-800001-42-7B"
        reconstructed = CanonicalAddress.model_validate(data)
        assert reconstructed.sap_premise_id == sample_canonical_address.sap_premise_id


class TestSearchModels:
    """Test suite for SearchQuery, CandidateMatch, SearchResult, and BatchRequest."""

    def test_valid_search_query(self) -> None:
        """Test valid SearchQuery construction."""
        query = SearchQuery(raw_address="42 MG Road Patna", max_results=10)
        assert query.raw_address == "42 MG Road Patna"
        assert query.max_results == 10
        assert query.tier_limit is None
        assert query.context == {}

    def test_search_query_min_length_validation(self) -> None:
        """Test that query strings under 3 characters are rejected."""
        with pytest.raises(ValidationError):
            SearchQuery(raw_address="ab")

    def test_search_query_max_length_validation(self) -> None:
        """Test that query strings over 500 characters are rejected."""
        with pytest.raises(ValidationError):
            SearchQuery(raw_address="a" * 501)

    def test_candidate_match_confidence_bounds(self) -> None:
        """Test confidence score validation between 0.0 and 1.0."""
        valid_match = CandidateMatch(
            sap_premise_id="PR-800001-42-7B",
            canonical_address="42 Mahatma Gandhi Road, Flat 7B, Patna 800001",
            confidence_score=0.95,
            match_tier=1,
        )
        assert valid_match.confidence_score == 0.95
        assert valid_match.confidence_degraded is False

        with pytest.raises(ValidationError):
            CandidateMatch(
                sap_premise_id="PR-1",
                canonical_address="Addr",
                confidence_score=1.5,
                match_tier=1,
            )

        with pytest.raises(ValidationError):
            CandidateMatch(
                sap_premise_id="PR-1",
                canonical_address="Addr",
                confidence_score=-0.1,
                match_tier=1,
            )

    def test_search_result_model(self) -> None:
        """Test constructing full SearchResult model."""
        match = CandidateMatch(
            sap_premise_id="PR-800001-42-7B",
            canonical_address="42 Mahatma Gandhi Road, Flat 7B, Patna 800001",
            confidence_score=0.96,
            match_tier=1,
        )
        result = SearchResult(
            query="Flat 7B, 42 Gandhi Rd Patna",
            candidates=[match],
            resolved=match,
            latency_ms=4.2,
            tiers_invoked=[0, 1],
            pincode_missing=False,
        )
        assert result.query == "Flat 7B, 42 Gandhi Rd Patna"
        assert len(result.candidates) == 1
        assert result.resolved is not None
        assert result.resolved.sap_premise_id == "PR-800001-42-7B"
        assert result.tiers_invoked == [0, 1]

    def test_batch_request_validation(self) -> None:
        """Test BatchRequest validation for empty and valid address lists."""
        with pytest.raises(ValidationError):
            BatchRequest(addresses=[])

        q = SearchQuery(raw_address="42 MG Road Patna")
        batch = BatchRequest(addresses=[q], callback_url="https://api.example.com/webhook")
        assert len(batch.addresses) == 1
        assert batch.callback_url == "https://api.example.com/webhook"
