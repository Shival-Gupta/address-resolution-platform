# implementation_plan.md — Granular Phased Build Checklist

> **Rule:** Do NOT start a new phase until ALL items in the current phase pass their verification commands.  
> **Convention:** Mark `[x]` when done. Mark `[~]` when in-progress.

---

## Phase 1: Foundation — Schemas, Config & Mock Data

### 1.1 Project Scaffolding
- [x] Create directory structure as defined in `architecture.md` (all `__init__.py` files included)
- [x] Create `.env.example` with all required env var keys (no values)
- [x] Create `requirements.txt` with pinned versions from tech stack
- [x] Create `pyproject.toml` with `ruff`, `mypy`, `pytest` configuration

**Verify:**
```bash
python -c "import app" 
ruff check app/              # 0 errors
mypy app/ --ignore-missing-imports  # 0 errors
```

---

### 1.2 `app/core/config.py` — Settings
- [x] Implement `Settings(BaseSettings)` with all env vars:
  - `GEMINI_API_KEY`, `OPENAI_API_KEY`, `EMBEDDING_MODEL`, `LLM_MODEL`
  - `DUCKDB_PATH`, `SAP_DSN`, `GIS_DB_URL`
  - `TIER1_CONFIDENCE_THRESHOLD` (default: 0.92), `TIER2_CONFIDENCE_THRESHOLD` (default: 0.88)
  - `LLM_FALLBACK_ENABLED` (default: True), `CIRCUIT_BREAKER_THRESHOLD` (default: 5 failures)
  - `API_KEY`, `LOG_LEVEL`, `PORT`, `WORKERS`
- [x] Use `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`
- [x] Create `get_settings()` function with `@lru_cache()`

**Verify:**
```bash
python -c "from app.core.config import get_settings; s = get_settings(); print(s.model_dump())"
```

---

### 1.3 `app/models/address.py` + `app/models/search.py` — Pydantic Schemas
- [x] Implement `AddressSlots` with all 9 fields + `pincode_missing` flag
- [x] Implement `CanonicalAddress` with `sap_premise_id`, `slots`, `embedding`, `geohash`, `source_db`
- [x] Implement `SearchQuery` with validation: `min_length=3`, `max_length=500`
- [x] Implement `CandidateMatch` with `confidence_degraded` flag
- [x] Implement `SearchResult` with `tiers_invoked: list[int]`
- [x] Add `model_config = ConfigDict(frozen=True)` to all response models

**Verify:**
```bash
python -c "
from app.models.address import CanonicalAddress, AddressSlots
from app.models.search import SearchQuery, SearchResult
print('All schemas import cleanly')
"
mypy app/models/ --strict
```

---

### 1.4 `app/db/mock_data.py` — Synthetic SAP Data Generator
- [x] Generate 10,000 canonical `CanonicalAddress` records covering:
  - 5+ Indian states, 20+ cities, real pincodes
  - Mix of `source_db`: "SAP_HANA", "GIS_POSTGIS", "BILLING_ORACLE"
- [x] For each canonical address, generate 8 permutations (abbreviated, jumbled, compact, etc.) as the test set
- [x] Seed must be deterministic (`--seed` CLI arg)
- [x] Write canonical records into DuckDB; write permutations into `tests/fixtures/permutations.json`
- [x] Use `click` for CLI: `python app/db/mock_data.py --records 10000 --seed 42`

**Verify:**
```bash
python app/db/mock_data.py --records 1000 --seed 42
python -c "
import duckdb
conn = duckdb.connect('./data/addresses.db')
count = conn.execute('SELECT COUNT(*) FROM addresses').fetchone()[0]
assert count == 1000, f'Expected 1000, got {count}'
print(f'DuckDB seeded: {count} records')
"
```

---

## Phase 2: Tier 0 — Normalizer Engine

### 2.1 `app/engines/normalizer.py`
- [x] **Abbreviation Dictionary** — minimum entries:
  ```python
  # Street types
  "rd" → "road", "st" → "street", "ave" → "avenue", "blvd" → "boulevard",
  "ln" → "lane", "dr" → "drive", "marg" → "road"
  # Sub-premise
  "fl" → "flat", "apt" → "apartment", "ste" → "suite", "#" → "flat"
  # Indian-specific
  "mg" → "mahatma gandhi", "jl" → "jawaharlal", "nr" → "near",
  "opp" → "opposite", "br" → "bihar", "mh" → "maharashtra",
  "dl" → "delhi", "ka" → "karnataka", "in" → "india"
  # Country/State abbreviations as two-letter codes
  ```
- [x] **Pincode Extractor:** regex `r'\b[1-9][0-9]{5}\b'` — captures first match
- [x] **Punctuation Normalizer:** strip `#`, `-`, `.`, `(`, `)`, `,` → replace with space
- [x] **Sub-premise Normalizer:** `#7-B` → `flat 7b`, `7/B` → `flat 7b`
- [x] **Slot Extractor:** heuristic rules to populate `AddressSlots`:
  - Number before street keyword → `premise_number`
  - Alphanumeric code after flat/apt/# → `flat_no`
  - 6-digit number → `pincode`
  - Known city/state from lookup table → `city`, `state`
- [x] **Token Sorter:** generate `normalized_tokens = sorted(all_tokens)` for Token Set Ratio
- [x] All functions are pure (no side effects, no I/O)

**Verify:**
```bash
pytest tests/unit/test_normalizer.py -v
# Must pass ALL of these input/output pairs:
# "#7-B, 42, M. Gandhi Rd., Patna (800001)" → pincode="800001", flat_no="7b", street="mahatma gandhi road"
# "Flat 7B, 42 Gandhi Rd., 800001 Patna"    → same slots
# "42 MG Rd, #7B, Patna, BR 800001, IN"     → same slots
# "7B - 42 MG Road, Patna 800001, Bihar"    → same slots
```

---

## Phase 3: Tier 1 — Lexical Engine

### 3.1 `app/db/duckdb_client.py`
- [x] Implement async-compatible DuckDB connection wrapper
- [x] `init_schema()` — create `addresses` table + indexes as defined in `architecture.md`
- [x] `upsert_address(record: CanonicalAddress)` — INSERT OR REPLACE
- [x] `get_candidate_pool(pincode: str) → list[dict]` — pre-filter by pincode (max 15,000)
- [x] `batch_upsert(records: list[CanonicalAddress])` — transactional bulk insert

**Verify:**
```bash
python -c "
import asyncio
from app.db.duckdb_client import DuckDBClient
async def test():
    client = DuckDBClient(':memory:')
    await client.init_schema()
    print('Schema OK')
asyncio.run(test())
"
```

### 3.2 `app/engines/lexical.py`
- [x] Implement `token_set_ratio(a: str, b: str) → float` using `rapidfuzz.fuzz.token_set_ratio`
- [x] Implement `trigram_similarity(a: str, b: str) → float` using DuckDB `jaccard()` or manual trigram set
- [x] Implement `search(slots: AddressSlots, candidate_pool: list[dict], top_k: int) → list[CandidateMatch]`:
  - Score each candidate with weighted combo: `0.6 * token_set_ratio + 0.4 * trigram_similarity`
  - Return sorted list, top_k results
  - Mark `match_tier=1` on all results

**Verify:**
```bash
pytest tests/unit/test_lexical.py -v
# Key assertions:
# token_set_ratio("Flat 7B, 42 MG Rd", "42 MG Rd, Flat 7B") >= 0.95
# token_set_ratio("Mahatama Gandhi Road", "Mahatma Gandhi Road") >= 0.88
# Full benchmark: Tier1-only accuracy >= 87% on permutations.json
python scripts/benchmark.py --tiers 1 --output table
```

---

## Phase 4: Tier 2 — Semantic Vector Engine

### 4.1 `app/engines/semantic.py`
- [x] Implement `generate_embedding(text: str) → list[float]` using `google-genai` SDK
- [x] Implement `batch_embed(texts: list[str]) → list[list[float]]` — batch size max 64
- [x] **HARD GUARDRAIL:** Implement `apply_number_filter(candidate_pool, slots) → filtered_pool`:
  - Filter by `slots.premise_number` (exact match or None)
  - Filter by `slots.flat_no` (exact match or None)
  - Never skip this filter before cosine computation
- [x] Implement `cosine_similarity(a: list[float], b: list[float]) → float`
- [x] Implement `search(slots, filtered_candidates, top_k) → list[CandidateMatch]`:
  - Embed the normalized query string
  - Compute cosine similarity against pre-loaded candidate embeddings
  - Return scored candidates with `match_tier=2`
- [x] Implement Reciprocal Rank Fusion (RRF) to merge T1 and T2 scores:
  `rrf_score = 1/(k + rank_t1) + 1/(k + rank_t2)` where k=60

**Verify:**
```bash
pytest tests/unit/test_semantic.py -v
# Key assertions:
# cosine_similarity of embedded "42 MG Rd Flat 7B Patna" vs canonical > 0.85
# Flat 7A and Flat 7B have different top results (number filter working)
python scripts/benchmark.py --tiers 1,2 --output table
# Tier1+2 accuracy must be >= 98%
```

---

## Phase 5: Tier 3 — LLM Disambiguator + Hybrid Router

### 5.1 `app/engines/llm_fallback.py`
- [x] Implement `CircuitBreaker` class:
  - State: CLOSED (normal) / OPEN (failing) / HALF-OPEN (testing)
  - Open after N consecutive failures (configurable via `settings.CIRCUIT_BREAKER_THRESHOLD`)
  - Auto-reset to HALF-OPEN after 60 seconds
- [x] Implement `disambiguate(query: str, candidates: list[CandidateMatch]) → CandidateMatch`:
  - If `circuit_breaker.state == OPEN`: return best candidate with `confidence_degraded=True`
  - Build structured prompt with top-3 candidates
  - Call Gemini Flash with `response_mime_type="application/json"` and Pydantic schema
  - Validate response; on failure: increment circuit breaker counter; return degraded result

**Verify:**
```bash
pytest tests/unit/test_llm_fallback.py -v
# Test circuit breaker: mock 5 consecutive Gemini failures → state becomes OPEN
# Test degraded return: when OPEN, returns T1 best result with confidence_degraded=True
# Integration test with real Gemini: test_llm_fallback_integration.py (requires API key)
```

### 5.2 `app/engines/hybrid_router.py`
- [x] Implement `HybridRouter` class with injected engine dependencies
- [x] Implement `async resolve(query: SearchQuery) → SearchResult`:
  - Full cascade as defined in architecture.md State Flow section
  - Track `tiers_invoked` list
  - Record latency with `time.perf_counter()`
  - Add OpenTelemetry span per tier
- [x] Implement `async suggest(query: SearchQuery) → SearchResult`:
  - Same as resolve but max T1 only (unless `pincode_missing=True`)

**Verify:**
```bash
pytest tests/integration/test_hybrid_router.py -v
# Full accuracy test on permutations.json:
python scripts/benchmark.py --tiers all --output table
# Expected: >= 99.5% accuracy, p95 latency < 20ms (T1 path)
```

---

## Phase 6: FastAPI Application & API Layer

### 6.1 `app/main.py`
- [x] Implement `lifespan` context: init DuckDB, load settings, init AI clients on startup; clean up on shutdown
- [x] Add CORS middleware
- [x] Add request logging middleware (log: method, path, status, latency)
- [x] Mount API router at `/v1`

### 6.2 `app/api/v1/search.py`
- [x] `POST /v1/search/suggest` → calls `router.suggest()`
- [x] `POST /v1/search/resolve` → calls `router.resolve()`
- [x] `POST /v1/search/batch` → enqueue async job, return `202 { job_id }`
- [x] All routes use `Depends(get_settings)` for config, `Depends(get_db)` for DuckDB
- [x] All routes validate API key via `Depends(verify_api_key)`

### 6.3 `app/api/v1/admin.py`
- [x] `GET /v1/admin/health` → return system metrics (no auth for health check)
- [x] `POST /v1/admin/reindex` → trigger background task (admin auth required)

**Verify:**
```bash
uvicorn app.main:app --port 8000 &
pytest tests/integration/test_api_endpoints.py -v
# Test: POST /v1/search/resolve with all 8 permutations of base address → same SAP ID returned
curl -X POST http://localhost:8000/v1/search/resolve \
  -H "X-API-Key: test_key" \
  -H "Content-Type: application/json" \
  -d '{"raw_address": "Flat 7B, 42 Gandhi Rd., 800001 Patna, Bihar, India"}'
# Expected: sap_premise_id = "PR-800001-42-7B"
```

---

## Phase 7: Benchmarking & Final Validation

### 7.1 `scripts/benchmark.py`
- [x] Load all permutations from `tests/fixtures/permutations.json`
- [x] Run each against: Greedy Exact, Vanilla Levenshtein, Token Set Only, Full Hybrid
- [x] Collect: accuracy (%), p50/p95/p99 latency (ms), API cost estimate
- [x] Output: `pandas` DataFrame rendered with `tabulate` as markdown table

**Verify:**
```bash
python scripts/benchmark.py --output table
# Required results:
# | Greedy     | < 5%  accuracy | < 1ms  |
# | Levenshtein| ~55% accuracy  | ~8ms   |
# | Hybrid T1  | >87% accuracy  | <8ms   |
# | Full Hybrid| >99.5% accuracy| <20ms  |
```

### 7.2 Final System Verification
- [x] `pytest tests/ -v` → 0 failures
- [x] `ruff check app/ tests/ scripts/` → 0 errors
- [x] `mypy app/ --strict` → 0 errors
- [x] Benchmark table meets or exceeds targets
- [x] `GET /v1/admin/health` returns `status: healthy`
