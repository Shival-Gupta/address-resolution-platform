# CLAUDE.md — Agent Execution Contract
## Address Resolution Platform

> Read this file before writing a single line of code. These are hard constraints, not suggestions.

---

## IDENTITY & ROLE
You are the Lead Architect and Coder for an **enterprise production system**. Every decision must be made as if this code will serve 10M users and be audited by SAP integration engineers. No shortcuts, no shortcuts disguised as "simplifications."

---

## BUILD COMMANDS

```bash
# Install dependencies (always use venv)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# Run server
uvicorn app.main:app --reload --port 8000

# Run all tests
pytest tests/ -v --tb=short --asyncio-mode=auto

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests only
pytest tests/integration/ -v

# Run benchmark comparison
python scripts/benchmark.py

# Seed database
python app/db/mock_data.py

# Lint
ruff check app/ tests/ scripts/
ruff format app/ tests/ scripts/

# Type check
mypy app/ --strict --ignore-missing-imports
```

---

## ARCHITECTURE RULES (NON-NEGOTIABLE)

1. **4-Tier Cascade — Never Bypass:** Every search request MUST flow through T0 → T1 → T2 (if T1 < 0.92) → T3 (if T2 < 0.88). Never call LLM (T3) directly for a query unless T1 and T2 have run and failed.

2. **Hard Number Filter Before Vector Search:** In `semantic.py`, ALWAYS extract `premise_number` and `flat_no` from normalized slots and use them as SQL `WHERE` pre-filters on DuckDB before computing cosine similarity. Dense embeddings are number-blind. Failure to do this is an architecture defect.

3. **Circuit Breaker on Tier 3:** `llm_fallback.py` must implement a circuit breaker (fail-open). If Gemini/OpenAI returns an error or times out (>3s), the system MUST return the best T1/T2 result with `confidence_degraded=True` flag — never return a 500 to the caller.

4. **Pydantic V2 Everywhere:** All request/response models, internal data structures, and settings MUST use Pydantic V2 `BaseModel` or `BaseSettings`. No raw dicts passed between modules. Use `model_validate()`, not `parse_obj()`.

5. **Async All I/O:** All DB reads, HTTP calls (LLM API, embedding API), and file I/O must use `async`/`await`. No blocking `requests` library. Use `httpx.AsyncClient` exclusively.

6. **No Global State:** Do not use module-level global variables for DuckDB connection or AI client. Use FastAPI `lifespan` context and dependency injection via `Depends()`.

7. **Pincode is the Spatial Anchor:** Every search query that does NOT contain a valid 6-digit Indian pincode must be flagged with `pincode_missing=True`. The system must still attempt resolution but must NOT claim confidence >0.7 without a pincode.

---

## FILE CONVENTIONS

| Pattern | Rule |
|---------|------|
| `engines/*.py` | One engine class per file. No cross-engine imports (except `normalizer.py` which is imported by all). |
| `models/*.py` | Only Pydantic model definitions. No logic. No imports from `engines/`. |
| `api/v1/*.py` | Only FastAPI route definitions. Business logic lives in engines, not routes. |
| `db/*.py` | Only database interaction code. No search logic. |

---

## WHAT NOT TO DO

- **Never** use `import *`
- **Never** catch bare `except:` — always catch specific exceptions and log them
- **Never** hardcode API keys, thresholds, or model names — all in `config.py` via env vars
- **Never** return raw exception tracebacks to the API caller — use structured error responses
- **Never** skip writing a test for a new engine function
- **Never** call embedding API in a loop without batching (batch size: 64 max)

---

## TEST REQUIREMENTS

Every PR must:
1. Pass `pytest tests/unit/` with 0 failures
2. Pass `mypy app/ --strict` with 0 errors
3. Demonstrate benchmark accuracy ≥87% on Tier 1 alone, ≥99% on full hybrid
4. Include a new test case for every new address permutation pattern discovered

---

## COMMIT MESSAGE FORMAT

```
feat(engine): add trigram indexing to lexical.py
fix(tier3): handle Gemini timeout with circuit breaker fallback
test(normalizer): add 23 new abbreviation expansion cases
refactor(router): extract confidence arbitration to separate method
docs(api): update /resolve endpoint response schema
```
