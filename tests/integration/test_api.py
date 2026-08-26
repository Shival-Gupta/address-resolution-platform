# File: tests/integration/test_api.py
"""Integration tests for FastAPI REST API endpoints.

Tests full HTTP lifecycle using httpx.AsyncClient across authentication,
search resolution, typeahead suggestions, batch jobs, health checks, and admin endpoints.
"""

from __future__ import annotations

import httpx
import pytest

from app.db.duckdb_client import DuckDBClient
from app.db.mock_data import generate_permutations
from app.main import app
from app.models.address import CanonicalAddress
from app.pipeline.orchestrator import SearchOrchestrator

AUTH_HEADERS = {"X-API-Key": "test_api_key"}
BEARER_HEADERS = {"Authorization": "Bearer test_api_key"}


@pytest.fixture
async def async_client(sample_canonical_address: CanonicalAddress) -> httpx.AsyncClient:
    """Create configured async HTTP test client with seeded in-memory database."""
    db_client = DuckDBClient(":memory:")
    await db_client.init_schema()
    await db_client.upsert_address(sample_canonical_address)

    orchestrator = SearchOrchestrator(db_client=db_client)

    app.state.db_client = db_client
    app.state.orchestrator = orchestrator

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    db_client.close()


class TestSystemHealthEndpoints:
    """Test public health and metrics endpoints."""

    @pytest.mark.asyncio
    async def test_root_health_no_auth(self, async_client: httpx.AsyncClient) -> None:
        """Verify root /health responds 200 without authentication."""
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_v1_admin_health_no_auth(self, async_client: httpx.AsyncClient) -> None:
        """Verify /v1/health responds with system metrics without authentication."""
        resp = await async_client.get("/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "duckdb_records" in data
        assert "circuit_breaker_state" in data

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, async_client: httpx.AsyncClient) -> None:
        """Verify /metrics responds with runtime status."""
        resp = await async_client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


class TestAuthentication:
    """Test API Key and Bearer token security enforcement."""

    @pytest.mark.asyncio
    async def test_resolve_missing_api_key_returns_401(
        self, async_client: httpx.AsyncClient
    ) -> None:
        """Verify request without API key returns 401 Unauthorized."""
        payload = {"raw_address": "42 MG Road Patna 800001"}
        resp = await async_client.post("/v1/resolve", json=payload)
        assert resp.status_code == 401
        assert "Invalid or missing API key" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_resolve_invalid_api_key_returns_401(
        self, async_client: httpx.AsyncClient
    ) -> None:
        """Verify request with invalid API key returns 401 Unauthorized."""
        payload = {"raw_address": "42 MG Road Patna 800001"}
        resp = await async_client.post(
            "/v1/resolve", json=payload, headers={"X-API-Key": "wrong_key"}
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_resolve_valid_bearer_token_succeeds(
        self, async_client: httpx.AsyncClient
    ) -> None:
        """Verify request with Bearer authorization header succeeds."""
        payload = {"raw_address": "42 MG Road Patna 800001"}
        resp = await async_client.post("/v1/resolve", json=payload, headers=BEARER_HEADERS)
        assert resp.status_code == 200


class TestSearchEndpoints:
    """Test address search and suggestion endpoints."""

    @pytest.mark.asyncio
    async def test_resolve_endpoint_success(
        self, async_client: httpx.AsyncClient, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Verify full address resolution returns resolved SAP Premise ID."""
        payload = {"raw_address": "42 Mahatma Gandhi Road, Flat 7B, Patna, Bihar 800001"}
        resp = await async_client.post("/v1/resolve", json=payload, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved"] is not None
        assert data["resolved"]["sap_premise_id"] == sample_canonical_address.sap_premise_id
        assert data["resolved"]["confidence_score"] >= 0.90
        assert data["pincode_missing"] is False
        assert "X-Process-Time-Ms" in resp.headers

    @pytest.mark.asyncio
    async def test_suggest_typeahead_endpoint(
        self, async_client: httpx.AsyncClient, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Verify fast typeahead suggestions return candidate list."""
        payload = {"raw_address": "42 MG Rd 800001", "max_results": 3}
        resp = await async_client.post("/v1/suggest", json=payload, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["candidates"]) >= 1
        assert data["candidates"][0]["sap_premise_id"] == sample_canonical_address.sap_premise_id

    @pytest.mark.asyncio
    async def test_batch_endpoint_returns_202_accepted(
        self, async_client: httpx.AsyncClient
    ) -> None:
        """Verify batch endpoint accepts jobs and returns 202 Accepted."""
        payload = {
            "addresses": [
                {"raw_address": "42 MG Road Patna 800001"},
                {"raw_address": "10 Boring Road Patna 800001"},
            ]
        }
        resp = await async_client.post("/v1/batch", json=payload, headers=AUTH_HEADERS)

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "QUEUED"
        assert "job_id" in data
        assert data["total_records"] == 2

    @pytest.mark.asyncio
    async def test_admin_reindex_endpoint(self, async_client: httpx.AsyncClient) -> None:
        """Verify admin reindex triggers background task with 202 response."""
        resp = await async_client.post("/v1/admin/reindex", headers=AUTH_HEADERS)
        assert resp.status_code == 202
        assert resp.json()["status"] == "REINDEXING_STARTED"

    @pytest.mark.asyncio
    async def test_all_eight_permutations_via_http_api(
        self, async_client: httpx.AsyncClient, sample_canonical_address: CanonicalAddress
    ) -> None:
        """Verify all 8 address permutation patterns resolve to target SAP ID via HTTP API."""
        permutations = generate_permutations(sample_canonical_address)

        for perm in permutations:
            payload = {"raw_address": perm["input"]}
            resp = await async_client.post("/v1/resolve", json=payload, headers=AUTH_HEADERS)
            assert resp.status_code == 200
            data = resp.json()
            assert data["resolved"] is not None, (
                f"Failed to resolve permutation {perm['type']}: {perm['input']}"
            )
            assert data["resolved"]["sap_premise_id"] == sample_canonical_address.sap_premise_id, (
                f"Resolved wrong ID for permutation {perm['type']}"
            )
