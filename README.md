# Consilium

Multi-LLM council for developer product concept work.

## Status

Phase 1 — Foundation (in progress).

## Setup

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Copy `.env.example` → `.env` and fill in API keys.

## Running tests

```bash
pytest                  # unit tests only
pytest -m integration   # real API smoke tests (requires keys in env)
```
