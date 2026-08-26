# TODO.md — Project Backlog

> Flat checklist. One item per line. No nesting. No priorities implied by order within a section.  
> Add new items at the bottom of the relevant section. Never delete completed items — mark `[x]`.

---

## Phase 1: Foundation

- [x] Create full directory structure with all `__init__.py` files
- [x] Write `requirements.txt` with all pinned versions
- [x] Write `pyproject.toml` with ruff, mypy, pytest config
- [x] Write `.env.example` with all required keys and inline comments
- [x] Write `app/core/config.py` — `Settings(BaseSettings)` with `@lru_cache`
- [x] Write `app/core/exceptions.py` — custom exception hierarchy
- [x] Write `app/models/address.py` — `AddressSlots`, `CanonicalAddress`
- [x] Write `app/models/search.py` — `SearchQuery`, `CandidateMatch`, `SearchResult`
- [x] Write `app/db/mock_data.py` — 10k synthetic records + 8 permutations each
- [x] Write `tests/conftest.py` — shared fixtures (in-memory DuckDB, sample addresses)
- [x] Write `docker-compose.yml` — app + optional Kafka sidecar for local CDC simulation

---

## Phase 2: Tier 0 — Normalizer

- [x] Write `app/engines/normalizer.py` — full normalizer implementation
- [x] Build abbreviation dictionary: minimum 60 entries covering Indian address types
- [x] Implement pincode regex extractor (`\b[1-9][0-9]{5}\b`)
- [x] Implement punctuation stripper + case folder
- [x] Implement sub-premise standardizer (`#7-B` → `7b`)
- [x] Implement slot extractor (heuristic rules for street, flat, city, state)
- [x] Implement sorted token list generator
- [x] Write `tests/unit/test_normalizer.py` — minimum 30 parametrized test cases
- [x] Validate all 8 permutation types of base address normalize to identical slots

---

## Phase 3: Tier 1 — Lexical Engine

- [x] Write `app/db/duckdb_client.py` — async wrapper, schema init, upsert, bulk insert
- [x] Write `app/engines/lexical.py` — token set ratio + trigram similarity
- [x] Implement `get_candidate_pool()` with pincode pre-filter in DuckDB
- [x] Implement weighted score combination (0.6 token_set + 0.4 trigram)
- [x] Write `tests/unit/test_lexical.py` — token set ratio edge cases, trigram accuracy
- [x] Verify Tier 1 standalone accuracy >= 87% on permutations test set

---

## Phase 4: Tier 2 — Semantic Engine

- [x] Write `app/engines/semantic.py` — embedding generation + cosine similarity
- [x] Implement `batch_embed()` with max 64 texts per call
- [x] Implement `apply_number_filter()` — hard filter on premise_number + flat_no before cosine
- [x] Implement RRF fusion of T1 and T2 scores (k=60)
- [x] Pre-generate embeddings for all 10k mock records during `mock_data.py` seed
- [x] Store 768-dim float arrays in DuckDB `FLOAT[768]` column
- [x] Write `tests/unit/test_semantic.py` — number filter, cosine ranking, batch embed
- [x] Verify Tier 1+2 combined accuracy >= 98% on permutations test set

---

## Phase 5: Tier 3 + Hybrid Router

- [x] Write `app/engines/llm_fallback.py` — circuit breaker + Gemini structured output
- [x] Implement `CircuitBreaker` state machine (CLOSED/OPEN/HALF-OPEN)
- [x] Implement disambiguation prompt template with top-3 candidates
- [x] Enforce Gemini response schema with Pydantic model
- [x] Write `app/engines/hybrid_router.py` — full cascade orchestration
- [ ] Add OpenTelemetry spans per tier in `hybrid_router.py`
- [x] Write `tests/unit/test_llm_fallback.py` — circuit breaker state transitions
- [x] Write `tests/integration/test_hybrid_router.py` — end-to-end with mocked LLM
- [x] Verify full hybrid accuracy >= 99.5% on permutations test set

---

## Phase 6: API Layer

- [x] Write `app/main.py` — lifespan, CORS, logging middleware, router mount
- [x] Write `app/core/auth.py` — API key + Bearer token validation middleware
- [x] Write `app/api/v1/search.py` — `/suggest`, `/resolve`, `/batch` routes
- [x] Write `app/api/v1/admin.py` — `/health`, `/reindex` routes
- [x] Write `tests/integration/test_api_endpoints.py` — all routes with TestClient
- [x] Verify all 8 address permutations of base address return same SAP Premise ID via API

---

## Phase 7: Benchmarking & Ops

- [x] Write `scripts/benchmark.py` — Greedy vs Levenshtein vs T1 vs Full Hybrid
- [x] Output benchmark as pandas DataFrame rendered with tabulate (markdown table)
- [x] Write `scripts/sync_cron.py` — checksum reconciliation + HNSW reindex
- [x] Write `app/db/multi_db_federator.py` — stub connectors for SAP/PostGIS/Oracle
- [x] Write `app/core/telemetry.py` — OpenTelemetry init + span helpers

---

## Technical Debt & Future Improvements

- [ ] Replace DuckDB Tier 1 with Typesense for production-grade concurrent fuzzy search
- [ ] Add landmark-based fallback when pincode AND city are both missing
- [ ] Add Hindi/Devanagari transliteration support (e.g., "महात्मा गांधी" → "Mahatma Gandhi")
- [ ] Add phonetic matching (Soundex/Metaphone) for vernacular transcription errors
- [ ] Implement real Kafka CDC pipeline with Debezium connector configs
- [ ] Add `/v1/jobs/{job_id}` polling endpoint for batch requests
- [ ] Add Prometheus metrics endpoint at `/metrics`
- [ ] Add response caching layer (Redis) for frequently queried pincodes
- [ ] Fine-tune embedding model on domain-specific Indian address corpus
- [ ] Add address validation mode: verify a given address exists in SAP (not just search)
- [ ] Build admin dashboard (React or Streamlit) for benchmark visualization
- [ ] Document SAP RFC/HANA connector setup for production deployment
- [ ] Write Helm chart for Kubernetes deployment
- [ ] Add rate limiting per API key (100 req/s default)
