# File: tests/conftest.py
"""Pytest fixtures for Address Resolution Platform test suite.

Provides reusable fixtures for Settings, in-memory DuckDB database connections,
and canonical address and slot instances.
"""

from __future__ import annotations

from collections.abc import Generator

import duckdb
import pytest

from app.core.config import Settings
from app.db.mock_data import init_duckdb_schema
from app.models.address import AddressSlots, CanonicalAddress
from app.models.search import SearchQuery


@pytest.fixture
def test_settings() -> Settings:
    """Fixture providing isolated Settings for test execution."""
    return Settings(
        GEMINI_API_KEY="test_gemini_key",
        OPENAI_API_KEY="test_openai_key",
        DUCKDB_PATH=":memory:",
        API_KEY="test_api_key",
        TIER1_CONFIDENCE_THRESHOLD=0.92,
        TIER2_CONFIDENCE_THRESHOLD=0.88,
        LOG_LEVEL="DEBUG",
    )


@pytest.fixture
def in_memory_db() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Fixture providing an initialized in-memory DuckDB connection."""
    conn = duckdb.connect(":memory:")
    init_duckdb_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_slots() -> AddressSlots:
    """Fixture providing a sample normalized AddressSlots instance."""
    return AddressSlots(
        raw_input="Flat 7B, 42 Mahatma Gandhi Road, Patna 800001, Bihar, India",
        pincode="800001",
        pincode_missing=False,
        premise_number="42",
        flat_no="7b",
        street="mahatma gandhi road",
        landmark="near gandhi maidan",
        city="patna",
        state="bihar",
        country="india",
        normalized_tokens=[
            "42",
            "7b",
            "bihar",
            "flat",
            "gandhi",
            "india",
            "mahatma",
            "patna",
            "road",
        ],
    )


@pytest.fixture
def sample_canonical_address(sample_slots: AddressSlots) -> CanonicalAddress:
    """Fixture providing a sample CanonicalAddress model."""
    return CanonicalAddress(
        sap_premise_id="PR-800001-42-7B",
        full_address="42 Mahatma Gandhi Road, Flat 7B, Patna, Bihar 800001, India",
        slots=sample_slots,
        embedding=[0.0] * 768,
        geohash="h3_r7_test",
        source_db="SAP_HANA",
    )


@pytest.fixture
def sample_search_query() -> SearchQuery:
    """Fixture providing a sample SearchQuery model."""
    return SearchQuery(
        raw_address="Flat 7B, 42 Gandhi Rd., 800001 Patna",
        max_results=5,
        tier_limit=None,
        context={"city_hint": "Patna"},
    )
