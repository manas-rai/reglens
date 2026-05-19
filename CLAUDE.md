# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**reglens** — multi-agent regulatory compliance automation. See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the full architecture and phased build plan.

## Commands

```bash
# Install / sync deps
uv sync --all-extras
# macOS note: hatchling editable installs get the macOS hidden chflag set,
# which Python's site module skips. Fix with:
#   chflags nohidden .venv/lib/python3.11/site-packages/_editable_impl_reglens.pth
# pytest sets PYTHONPATH=src via pyproject.toml so it's unaffected.
# For `uv run python` scripts outside pytest, use: PYTHONPATH=src uv run python ...

# Run all unit tests
uv run pytest tests/unit -v

# Run with coverage
uv run pytest tests/unit --cov --cov-report=term-missing

# Run a single test file
uv run pytest tests/unit/test_smoke.py -v

# Lint
uv run ruff check .
uv run ruff format --check .

# Auto-fix lint issues
uv run ruff check --fix .
uv run ruff format .

# Type check
uv run mypy src/reglens

# Run the full stack locally
cp .env.example .env   # fill in API keys
docker compose up

# Run database migrations
docker compose run --rm migrate
# or directly against a running Postgres:
uv run alembic upgrade head

# Generate a new migration
uv run alembic revision --autogenerate -m "describe_change"
```

## Architecture

See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the full design. Summary:

- **FastAPI** (`src/reglens/api/`) — HTTP surface; `POST /runs`, `GET /runs/{id}`, `POST /runs/{id}/approve`, SSE `/runs/{id}/events`
- **LangGraph Supervisor** (`src/reglens/supervisor/`) — orchestrates the compliance pipeline via a `StateGraph` with `PostgresSaver` checkpointing and `interrupt()` for HITL
- **ADK Ingestion Agent** (`src/reglens/agents/ingestion/`) — Gemini multimodal PDF → `list[Obligation]`, exposed as an A2A server on port 8001
- **ADK Risk Scorer Agent** (`src/reglens/agents/risk_scorer/`) — Gemini-backed `GapResult` → `RiskScore`, exposed as an A2A server on port 8002
- **Knowledge Agent / RAG** (`src/reglens/rag/`) — pgvector semantic search over the org's policy corpus; in-process LangGraph node
- **Gap Analyzer** (`src/reglens/agents/gap_analyzer/`) — Claude (instructor) classifies COMPLIANT/PARTIAL GAP/GAP/NOT APPLICABLE; in-process fan-out via `Send()`
- **A2A layer** (`src/reglens/a2a/`) — minimal JSON-RPC 2.0 server/client for cross-framework calls; OTel spans on every call
- **Persistence** (`src/reglens/persistence/`) — SQLAlchemy + Alembic; `runs`, `audit_log`, `cost_records`, `policies` (pgvector) tables
- **Observability** (`src/reglens/observability/`) — structlog JSON logging, OTel tracing (console in dev, OTLP in prod), LangSmith for LangGraph nodes

## Key conventions

- `src/reglens/config.py` — `get_settings()` is the single source of truth for all config; all env vars documented in `.env.example`
- All LLM outputs are Pydantic-validated — no raw JSON parsing anywhere
- A2A is the only network boundary between LangGraph and ADK processes
- Tests under `tests/unit/` require no external services. Tests marked `integration` need docker-compose. Tests marked `e2e` run the full pipeline.
- The `alembic.ini` `sqlalchemy.url` is overridden at runtime from `DATABASE_URL` env var — never put credentials in `alembic.ini`

## Current phase

**Phase 0 — Foundation** (complete). Start Phase 1 (Vertical MVP) next: schemas → supervisor graph → A2A layer → agents → FastAPI routes → fixtures.
