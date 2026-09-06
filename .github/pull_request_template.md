## Description
Briefly explain the problem addressed, resolution tier affected (Exact, Fuzzy, Semantic, ML Rerank), and changes introduced.

## Type of Change
- [ ] Core matcher optimization / bug fix
- [ ] New normalization / parsing heuristic
- [ ] Benchmark / evaluation suite update
- [ ] Documentation or configuration update

## Checklist
- [ ] Tests pass locally (`pytest tests/ -v`)
- [ ] Type annotations pass strictly (`mypy app/ --strict`)
- [ ] Ruff linting and formatting pass (`ruff check app/ tests/` && `ruff format --check app/ tests/`)
- [ ] No performance regression on address matching benchmark
- [ ] Commit is cryptographically signed
