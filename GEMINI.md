# GEMINI.md — Agent Execution Contract
## Address Resolution Platform

> Ingest CLAUDE.md first. This file extends it with Gemini-specific preferences and tool boundaries.

---

## ROLE
You are the Lead Architect, Senior Developer, and Code Reviewer. You produce enterprise-grade, production-ready Python. Every response must be complete, compilable, and correct. No placeholders (`# TODO`, `pass`, `...`).

---

## BUILD & RUN COMMANDS

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt

# Development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Tests
pytest tests/ -v --asyncio-mode=auto
pytest tests/unit/test_normalizer.py -v        # Single module test
pytest tests/ -k "test_jumbled" -v             # Run by keyword

# Benchmark
python scripts/benchmark.py --output table     # Print pandas/tabulate matrix
python scripts/benchmark.py --output csv       # Export CSV

# Seed data
python app/db/mock_data.py --records 10000 --seed 42

# Lint + format
ruff check . && ruff format .
mypy app/ --strict
```

---

## LANGUAGE & FRAMEWORK PREFERENCES

| Preference | Choice |
|-----------|--------|
| Python version | 3.11+ (use `match` statements, `tomllib`, `ExceptionGroup` where appropriate) |
| Type hints | Mandatory on ALL function signatures. Use `from __future__ import annotations` in every file. |
| Async framework | `asyncio` + `httpx.AsyncClient`. No `requests`, no `aiohttp`. |
| Pydantic | V2 exclusively. `model_validate()`, `model_dump()`. Not `parse_obj()`, `.dict()`. |
| DuckDB | Use parameterized queries only. Never f-string SQL. |
| LLM SDK | Use `google-genai` SDK for Gemini. Use structured output / response schema enforcement. |
| Error handling | Custom exception hierarchy in `app/core/exceptions.py`. Never bare `except`. |
| Logging | `structlog` or stdlib `logging` with JSON formatter. No `print()` statements in production code. |

---

## GEMINI API USAGE RULES

```python
# CORRECT: Use response_schema for structured output
from google.genai import types

response = client.models.generate_content(
    model=settings.LLM_MODEL,
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=DisambiguationResult,  # Pydantic model
        temperature=0.0,                        # Deterministic for disambiguation
        max_output_tokens=256,
    )
)

# WRONG: Never parse raw LLM text with json.loads() — use structured output
```

```python
# CORRECT: Batch embedding calls (max 64 per request)
embeddings = client.models.embed_content(
    model=settings.EMBEDDING_MODEL,
    contents=batch_of_texts[:64],
)

# WRONG: Never call embed_content() in a for loop per-item
```

---

## TOOL BOUNDARIES FOR CODING AGENTS

| Allowed | Not Allowed |
|---------|------------|
| Read any file in the project | Modify `.env` files directly |
| Create new files in `app/`, `tests/`, `scripts/` | Create files outside project root |
| Run `pytest`, `ruff`, `mypy`, `uvicorn` | Run `pip install` without updating `requirements.txt` |
| Run `python scripts/*.py` | Execute shell commands that modify system state |
| Append to `TODO.md` when discovering new tasks | Delete any existing test cases |

---

## ARCHITECTURE ENFORCEMENT (SAME AS CLAUDE.md)

Refer to `CLAUDE.md` for the full list. Summary:
1. 4-Tier cascade is mandatory — no shortcuts.
2. Hard number pre-filter before every vector search (number-blindness guardrail).
3. Circuit breaker on Tier 3 LLM — degrade gracefully, never 500.
4. No global mutable state — use FastAPI `lifespan` + `Depends()`.
5. All I/O is async — `httpx.AsyncClient` only.

---

## RESPONSE FORMAT FOR CODE OUTPUT

When writing code:
1. Always output the **complete file** — no partial snippets.
2. Include `# File: app/engines/lexical.py` as the first comment line.
3. Include module docstring explaining purpose, inputs, outputs, and which tier it handles.
4. After code, list: a) what was implemented, b) what test to run to verify, c) what the next file to implement is.
