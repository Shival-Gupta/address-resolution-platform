# File: app/models/address.py
"""Address data schemas for normalized slots and canonical SAP master records.

Defines AddressSlots (output of Tier 0 Normalizer) and CanonicalAddress
(canonical source of truth stored in DuckDB and replicated from SAP/GIS).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class AddressSlots(BaseModel):
    """Structured slot extraction output from Tier 0 Normalizer.

    Attributes:
        raw_input: Original raw address string prior to normalization.
        pincode: Extracted 6-digit Indian PIN code if present.
        pincode_missing: Flag indicating whether pincode was absent in input.
        premise_number: Extracted premise or building number (e.g. "42").
        flat_no: Extracted sub-premise or unit number (e.g. "7B").
        street: Extracted street or thoroughfare name.
        landmark: Extracted landmark or vicinity hint.
        city: Extracted city or town name.
        state: Extracted state or province name.
        country: Country name, defaults to "India".
        normalized_tokens: Lexicographically sorted token list for Token Set Ratio.
    """

    raw_input: str
    pincode: str | None = None
    pincode_missing: bool = False
    premise_number: str | None = None
    flat_no: str | None = None
    street: str | None = None
    landmark: str | None = None
    city: str | None = None
    state: str | None = None
    country: str = "India"
    normalized_tokens: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class CanonicalAddress(BaseModel):
    """SAP master address record representing the canonical source of truth.

    Attributes:
        sap_premise_id: Standardized premise identifier (PR-{PINCODE}-{PREMISE_NO}-{FLAT_NO}).
        full_address: Human-readable canonical address representation.
        slots: Structured AddressSlots corresponding to this master record.
        embedding: 768-dimensional dense vector representation (optional).
        geohash: H3 or spatial geohash at resolution 7 (optional).
        source_db: Source database identifier ("SAP_HANA", "GIS_POSTGIS", "BILLING_ORACLE").
        created_at: Record creation timestamp in UTC.
        updated_at: Record last update timestamp in UTC.
    """

    sap_premise_id: str
    full_address: str
    slots: AddressSlots
    embedding: list[float] | None = None
    geohash: str | None = None
    source_db: str = "SAP_HANA"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(frozen=True)
