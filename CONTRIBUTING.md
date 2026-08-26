# CONTRIBUTING.md — AI Coding Standards & Architectural Constraints

> **Applies to:** All human developers and autonomous AI coding agents (Claude Code, Antigravity, Cursor, Codex, Roo).

---

## Code Quality Standards

### Python Style
- **Python 3.11+** — use `match` statements, `ExceptionGroup`, `tomllib` where appropriate
- `from __future__ import annotations` at the top of every file
- Type hints on every function signature — no `Any` without explicit justification comment
- Line length: 100 characters maximum (`ruff` configured)
- **No `print()` in production code** — use `logging.getLogger(__name__)` or `structlog`
- **No `# type: ignore`** without a comment explaining why
- **No dead code** — remove commented-out code before commit

### Module Rules
```
Rule: One responsibility per module.
Rule: engines/* must not import from api/* (one-way dependency)
Rule: models/* must not import from engines/* or api/*
Rule: db/* must not import from engines/* or api/*
Rule: All cross-module communication via Pydantic models only
```

### Function Rules
- Max function length: **50 lines** (if longer, extract sub-functions)
- Max function arguments: **5** (use Pydantic model if more needed)
- Every public function must have a Google-style docstring:
  ```python
  def normalize(raw_address: str) -> AddressSlots:
      """Normalize a raw unstructured address into structured slots.
      
      Args:
          raw_address: Unstructured address string from user input.
          
      Returns:
          AddressSlots with extracted pincode, premise, street, city, state.
          
      Raises:
          NormalizationError: If raw_address is empty after stripping.
      """
  ```

---

## Architectural Constraints (Hard Rules)

| # | Constraint | Violation Consequence |
|---|-----------|----------------------|
| 1 | Never call Tier 3 (LLM) without Tier 1 and Tier 2 completing first | Revert and re-architect |
| 2 | Always apply number filter before vector cosine computation | Revert — creates number-blindness bug |
| 3 | Tier 3 must have circuit breaker fail-open | System becomes unavailable without it |
| 4 | All external I/O must be async | Blocks event loop under load |
| 5 | Pydantic V2 for all inter-module data | Type safety is non-negotiable |
| 6 | No hardcoded thresholds — all via `config.py` | Impossible to tune without redeployment |
| 7 | Parameterized SQL queries only | SQL injection vulnerability |
| 8 | API keys in env vars / `.env` only | Security breach |

---

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files | `snake_case.py` | `lexical.py`, `hybrid_router.py` |
| Classes | `PascalCase` | `HybridRouter`, `CanonicalAddress` |
| Functions | `snake_case` | `normalize_address()`, `get_candidate_pool()` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_BATCH_SIZE`, `DEFAULT_TOP_K` |
| Pydantic fields | `snake_case` | `sap_premise_id`, `flat_no` |
| API paths | `kebab-case` | `/v1/search/suggest`, `/v1/admin/reindex` |
| Test functions | `test_<what>_<condition>` | `test_normalize_jumbled_address()` |
| Test fixtures | `snake_case` (in `conftest.py`) | `duckdb_client`, `sample_addresses` |

---

## Testing Standards

### Coverage Requirements
- `engines/*.py`: **90% line coverage minimum**
- `models/*.py`: **100% (they're just schemas — trivial)**
- `api/v1/*.py`: **80% (tested via integration tests)**
- `db/*.py`: **85%**

### Test Structure
```python
# tests/unit/test_normalizer.py

import pytest
from app.engines.normalizer import normalize
from app.models.address import AddressSlots

class TestNormalizeAbbreviations:
    """Test that abbreviation expansion works correctly."""
    
    @pytest.mark.parametrize("raw,expected_street", [
        ("42 M.G. Rd, Patna 800001", "mahatma gandhi road"),
        ("42 MG Rd, Patna 800001",   "mahatma gandhi road"),
        ("42 mg rd, patna 800001",   "mahatma gandhi road"),
    ])
    def test_mg_road_variants(self, raw: str, expected_street: str) -> None:
        result = normalize(raw)
        assert result.street == expected_street
```

### What Must Be Tested
- Every entry in the abbreviation dictionary
- All 8 permutation types of the base address
- Edge cases: pincode missing, flat number missing, only city+state provided
- Circuit breaker: 5 consecutive LLM failures → OPEN state
- Vector number filter: `Flat 7A` and `Flat 7B` resolve to different records

### What Must NOT Be in Tests
- No `time.sleep()` in unit tests
- No real network calls in unit tests (mock all external APIs)
- No hardcoded absolute file paths (use `pathlib.Path(__file__).parent`)

---

## Commit Standards

### Format
```
<type>(<scope>): <short imperative description>

[Optional body: why this change was made]
[Optional footer: Breaking changes, issue refs]
```

### Types
| Type | Use For |
|------|---------|
| `feat` | New functionality |
| `fix` | Bug fix |
| `refactor` | Code restructure (no behavior change) |
| `test` | Add/modify tests |
| `docs` | Documentation only |
| `perf` | Performance improvement |
| `chore` | Build tooling, dependencies |

### Examples
```bash
git commit -m "feat(normalizer): add 47 Indian state/city abbreviation expansions"
git commit -m "fix(tier3): circuit breaker now correctly resets after 60s half-open"
git commit -m "perf(semantic): batch embedding calls reduce API latency by 40%"
git commit -m "test(hybrid_router): add integration test for all 8 address permutations"
```

### Rules
- Commit message subject line: max 72 characters
- One logical change per commit
- Tests must pass before committing (`pytest tests/unit/` minimum)
- Never commit `.env` files, API keys, or `*.db` files (check `.gitignore`)

---

## Pull Request Checklist

Before opening a PR, verify:
- [ ] `pytest tests/unit/` → 0 failures
- [ ] `ruff check app/ tests/ scripts/` → 0 errors
- [ ] `mypy app/ --strict` → 0 type errors
- [ ] All new functions have docstrings
- [ ] New architectural constraints (if any) added to `CONTRIBUTING.md`
- [ ] `TODO.md` updated if new backlog items discovered
- [ ] `CONTEXT.md` updated if new business rules discovered

---

## `.gitignore` Mandatory Entries

```
.env
*.db
*.duckdb
__pycache__/
.venv/
.mypy_cache/
.ruff_cache/
dist/
*.egg-info/
data/*.db
```
