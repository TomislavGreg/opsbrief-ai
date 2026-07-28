# OpsBrief AI: development guide

Conventions and commands for anyone working in this repository.

## Layout

```
src/opsbrief/          Application package
  api/                 FastAPI routers, one module per resource
  config.py            Environment-backed settings
  main.py              Application factory and module-level `app`
tests/                 Pytest suite mirroring the package layout
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

## Commands

```bash
uvicorn opsbrief.main:app --reload   # Run the API on http://127.0.0.1:8000
pytest                               # Full test suite
pytest tests/test_health.py          # One module
ruff check .                         # Lint
ruff check . --fix                   # Lint and autofix
ruff format .                        # Format
```

CI runs `ruff format --check .`, `ruff check .` and `pytest` on Python 3.12.

## Conventions

- Python 3.12. Standard library first, small focused dependencies only.
- Prefer plain functions and small modules over class hierarchies and frameworks.
- Pydantic models define every request and response body. Validate all input.
- Routers stay thin: parse and validate in the router, put logic in a service module.
- Type hints on every public function. Docstrings explain intent, not syntax.
- Tests cover behaviour, not implementation detail. Every changed behaviour gets a test.
- AI provider output is untrusted data. Validate and constrain it before use.
- Generated output must be traceable to the source event IDs that produced it.
- No secrets in the repository. `.env` is ignored; `.env.example` holds placeholders only.

## Branches and commits

Branch names: `feat/ai-xxx-short-description`, and likewise `fix/`, `test/`, `docs/`.

Conventional Commits, scoped to the area changed:

```
feat(briefs): generate prioritized daily summaries
fix(events): handle events with missing metadata
test(risks): cover overdue detection at the boundary
docs(readme): record AI-004 as done
```

`main` is always green. Changes reach it through a pull request, merged with
rebase-and-merge so history stays linear.

## Data policy

This is a public repository. It must never contain private, customer or
personal data. Sample events are synthetic.
