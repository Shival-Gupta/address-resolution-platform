# architecture.md — Complete Technical Specification
## Address Resolution Platform

---

## 1. System Overview

**Pattern:** 4-Tier Cascaded Hybrid Search Funnel  
**Data Flow:** Read-heavy system. Search indices are async-replicated from SAP/GIS source-of-truth.  
**Consistency Model:** Eventual consistency (Hot path: <500ms lag; Cold path: 24h batch).

---

## 2. Directory Structure (Canonical)

```
address-resolution-platform/
│
├── app/                            # Main application package
│   │
│   ├── main.py                     # FastAPI app factory, lifespan, CORS, middleware
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── search.py           # Search routes: /suggest, /resolve, /batch
│   │       └── admin.py            # Admin routes: /reindex, /health, /metrics
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Pydantic BaseSettings — all env vars live here
│   │   ├── auth.py                 # API key + Bearer token middleware
│   │   ├── exceptions.py           # Custom exception hierarchy
│   │   └── telemetry.py            # OpenTelemetry spans, metrics, logging
│   │
│   ├── engines/
│   │   ├── __init__.py
│   │   ├── normalizer.py           # Tier 0: Regex, abbreviation dict, slot extraction
│   │   ├── lexical.py              # Tier 1: DuckDB trigrams + token set ratio
│   │   ├── semantic.py             # Tier 2: Embedding generation + cosine HNSW
│   │   ├── llm_fallback.py         # Tier 3: Gemini/OpenAI structured cross-encoder
│   │   └── hybrid_router.py        # Cascade orchestrator + confidence arbitration
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── duckdb_client.py        # DuckDB init, schema creation, connection lifecycle
│   │   ├── multi_db_federator.py   # SAP HANA / PostGIS / Oracle read-only connectors
│   │   └── mock_data.py            # Synthetic address generator for dev/test
│   │
│   └── models/
│       ├── __init__.py
│       ├── address.py              # AddressSlots, CanonicalAddress, NormalizedAddress
│       └── search.py               # SearchQuery, SearchResult, CandidateMatch, BatchRequest
│
├── scripts/
│   ├── benchmark.py                # Comparative benchmark: Greedy vs Fuzzy vs Hybrid
│   └── sync_cron.py                # Nightly: checksum reconciliation + HNSW reindex
│
├── tests/
│   ├── conftest.py                 # pytest fixtures: DuckDB, mock client, sample data
│   ├── unit/
│   │   ├── test_normalizer.py      # All abbreviation + regex cases
│   │   ├── test_lexical.py         # Token set ratio + trigram accuracy
│   │   └── test_semantic.py        # Embedding pipeline + cosine ranking
│   └── integration/
│       ├── test_hybrid_router.py   # Full cascade with mocked LLM
│       └── test_api_endpoints.py   # FastAPI TestClient: all routes
│
├── .env.example
├── .cursorrules
├── requirements.txt
├── pyproject.toml
└── docker-compose.yml
```

---

## 3. Data Models (Pydantic V2)

### `app/models/address.py`

```python
class AddressSlots(BaseModel):
    """Output of Tier 0 Normalizer — structured slot extraction."""
    raw_input: str
    pincode: str | None                 # 6-digit Indian PIN
    pincode_missing: bool = False
    premise_number: str | None          # "42"
    flat_no: str | None                 # "7B"
    street: str | None                  # "Mahatma Gandhi Road"
    landmark: str | None                # "Near Gandhi Maidan"
    city: str | None                    # "Patna"
    state: str | None                   # "Bihar"
    country: str = "India"
    normalized_tokens: list[str]        # Sorted token list for Token Set Ratio

class CanonicalAddress(BaseModel):
    """SAP master record — source of truth stored in DuckDB."""
    sap_premise_id: str                 # "PR-800001-42-7B"
    full_address: str                   # Human-readable canonical string
    slots: AddressSlots
    embedding: list[float] | None       # 768-dim vector (null until indexed)
    geohash: str | None                 # H3 geohash at resolution 7
    source_db: str                      # "SAP_HANA" | "GIS_POSTGIS" | "BILLING_ORACLE"
    created_at: datetime
    updated_at: datetime
```

### `app/models/search.py`

```python
class SearchQuery(BaseModel):
    """Inbound search request."""
    raw_address: str = Field(..., min_length=3, max_length=500)
    max_results: int = Field(default=5, ge=1, le=20)
    tier_limit: int | None = Field(default=None, ge=0, le=3)  # Force stop at tier N
    context: dict[str, str] = {}       # Optional: {"city_hint": "Patna"}

class CandidateMatch(BaseModel):
    """A single resolved candidate from any tier."""
    sap_premise_id: str
    canonical_address: str
    confidence_score: float             # 0.0 – 1.0
    match_tier: int                     # 1, 2, or 3
    confidence_degraded: bool = False   # True if T3 circuit breaker fired
    match_rationale: str | None         # LLM explanation (T3 only)

class SearchResult(BaseModel):
    """Full API response."""
    query: str
    candidates: list[CandidateMatch]
    resolved: CandidateMatch | None     # Best single match (if confidence > threshold)
    latency_ms: float
    tiers_invoked: list[int]            # e.g., [0, 1] or [0, 1, 2, 3]
    pincode_missing: bool
```

---

## 4. API Routes

### `POST /v1/search/suggest`
- **Purpose:** Typeahead — fast, partial, top-5 results
- **SLA:** p95 < 20ms
- **Body:** `SearchQuery`  
- **Response:** `SearchResult` (max 5 candidates, T1 only unless pincode missing)

### `POST /v1/search/resolve`
- **Purpose:** Full resolution — single best match with SAP Premise ID
- **SLA:** p95 < 80ms
- **Body:** `SearchQuery`  
- **Response:** `SearchResult` (full cascade, single `resolved` candidate)

### `POST /v1/search/batch`
- **Purpose:** Bulk address resolution (async)
- **Body:** `BatchRequest { addresses: list[SearchQuery], callback_url: str | None }`
- **Response:** `202 Accepted { job_id: str }` — results delivered to callback or polled at `/v1/jobs/{job_id}`

### `GET /v1/admin/health`
- **Response:** `{ status, duckdb_records, embedding_index_size, tier_latency_p95_ms, circuit_breaker_state }`

### `POST /v1/admin/reindex`
- **Auth:** Admin API key required
- **Purpose:** Trigger full re-embedding of all DuckDB records

---

## 5. State Flow — Search Request Lifecycle

```
Client → POST /v1/search/resolve
│
├─ Auth Middleware (validate API key)
├─ Rate Limiter (100 req/s per key)
│
├─ [Tier 0] normalizer.normalize(raw_address)
│     - Extract pincode → if missing, flag & log
│     - Expand abbreviations (dict lookup)
│     - Extract slots: premise_no, flat, street, city, state
│     - Generate sorted token list
│     Output: AddressSlots
│
├─ Spatial Filter: DuckDB WHERE pincode = ?  → candidate_pool (max 15,000)
│
├─ [Tier 1] lexical.search(slots, candidate_pool)
│     - DuckDB trigram similarity SQL
│     - Token Set Ratio via RapidFuzz
│     - If best_score >= 0.92 → RETURN (skip T2, T3)
│     Output: list[CandidateMatch] sorted by score
│
├─ [Tier 2] semantic.search(slots, top_k_from_t1=20)
│     - Hard filter: WHERE premise_number = ? AND flat_no = ?
│     - Embed query with google-genai text-embedding-004
│     - Cosine similarity against HNSW index
│     - Fuse T1 + T2 scores with RRF
│     - If best_fused_score >= 0.88 → RETURN (skip T3)
│     Output: list[CandidateMatch] (fused scores)
│
├─ [Tier 3] llm_fallback.disambiguate(query, top3_candidates)
│     - Circuit breaker check (fail-open if breaker=OPEN)
│     - Build disambiguation prompt with top-3 candidates
│     - Call Gemini Flash with structured JSON schema
│     - Validate response with Pydantic
│     Output: CandidateMatch with rationale
│
└─ Build SearchResult → Return 200
```

---

## 6. DuckDB Schema

```sql
-- Main address table (canonical SAP records)
CREATE TABLE IF NOT EXISTS addresses (
    sap_premise_id   VARCHAR PRIMARY KEY,
    full_address     VARCHAR NOT NULL,
    pincode          VARCHAR(6),
    premise_number   VARCHAR,
    flat_no          VARCHAR,
    street           VARCHAR,
    city             VARCHAR,
    state            VARCHAR,
    normalized_str   VARCHAR,        -- space-joined sorted tokens
    embedding        FLOAT[768],     -- dense embedding vector
    geohash          VARCHAR,
    source_db        VARCHAR,
    created_at       TIMESTAMP,
    updated_at       TIMESTAMP
);

-- Trigram index on normalized_str for fast fuzzy matching
CREATE INDEX IF NOT EXISTS idx_normalized ON addresses(normalized_str);
CREATE INDEX IF NOT EXISTS idx_pincode    ON addresses(pincode);
CREATE INDEX IF NOT EXISTS idx_premise    ON addresses(pincode, premise_number, flat_no);
```

---

## 7. Multi-DB Ingestion Architecture

```
Source Systems:                Event Bus:              Search Index:
┌─────────────┐                                       ┌──────────────┐
│ SAP S/4HANA │──[Debezium CDC]──┐                   │ DuckDB OLAP  │
│ (HANA/DB2)  │                  │                   │ (Trigrams)   │
└─────────────┘                  ▼                   └──────┬───────┘
┌─────────────┐          ┌───────────────┐                  │
│ GIS PostGIS │──[PG CDC]─│ Kafka / Redis │──[Worker]───────┤
└─────────────┘          │    Streams    │         upsert  │
┌─────────────┐          └───────────────┘                  ▼
│ Oracle RDBMS│──[LogMiner]──┘                    ┌──────────────────┐
│ (Billing)   │                                   │ Embedding Store  │
└─────────────┘                                   │ (HNSW in DuckDB) │
                                                  └──────────────────┘
```

**Hot Path:** CDC event → Ingestion Worker → Normalize → Embed → Upsert → <500ms
**Cold Path:** Nightly cron → Full checksum → Re-embed stale records → Rebuild HNSW → Report drift
