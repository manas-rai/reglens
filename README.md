# RegLens

Multi-agent regulatory compliance automation. Feed it a regulatory PDF and your organization's control matrix — it extracts every obligation, checks each one against your policies, scores the gaps by regulatory risk, and produces a structured audit report. A human-in-the-loop gate lets a compliance reviewer approve, reject, or edit the draft before the report is finalized.

---

## How it works

```
PDF + Control Matrix
        │
        ▼
┌───────────────────────────────────────────────┐
│  FastAPI (port 8000)                          │
│  POST /runs  →  GET /runs/{id}/events (SSE)   │
└───────────────────┬───────────────────────────┘
                    │ kicks off async pipeline
                    ▼
┌───────────────────────────────────────────────┐
│  LangGraph Supervisor  (port 8010 internal)   │
│                                               │
│  ingest ──► retrieve policies ──► analyze     │
│                                    gaps       │
│                                      │        │
│                                      ▼        │
│                                  score risks  │
│                                      │        │
│                                      ▼        │
│                            generate report    │
│                            ── HITL interrupt ─┤
└───────┬─────────────────────────────┬─────────┘
        │ A2A / JSON-RPC 2.0          │ A2A
        ▼                             ▼
┌──────────────┐             ┌──────────────────┐
│  Ingestion   │             │  Risk Scorer     │
│  Agent       │             │  Agent           │
│  (port 8001) │             │  (port 8002)     │
│  Gemini      │             │  Gemini          │
│  multimodal  │             │  + risk rubric   │
└──────────────┘             └──────────────────┘
        │
        ▼
  list[Obligation]   ──►  pgvector RAG  ──►  GapResult[]
                          (policies)          (Claude)
```

**Five services, one database:**

| Service | Port | What it does |
|---|---|---|
| `reglens-api` | 8000 | REST + SSE surface; accepts runs, streams progress, serves reports |
| `reglens-supervisor` | 8010 | LangGraph graph; orchestrates the full pipeline |
| `reglens-adk-ingest` | 8001 | A2A agent: PDF → `list[Obligation]` via Gemini multimodal |
| `reglens-adk-risk` | 8002 | A2A agent: `GapResult` → `RiskScore` via Gemini + domain rubric |
| `postgres` | 5432 | LangGraph checkpoints, run state, pgvector policy embeddings, audit log |

---

## Quick start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Docker + Docker Compose](https://docs.docker.com/compose/)
- API keys: `GEMINI_API_KEY` (Google AI Studio), `ANTHROPIC_API_KEY`

### 1 — Configure environment

```bash
cp .env.example .env
# Edit .env and fill in:
#   GEMINI_API_KEY=...
#   ANTHROPIC_API_KEY=...
#   API_KEY=any-secret-you-choose
```

### 2 — Start all services

```bash
docker compose up -d
```

Postgres starts first; the other four services wait for it to be healthy before starting. Run `docker compose logs -f` to watch startup.

### 3 — Run database migrations

```bash
docker compose run --rm migrate
```

### 4 — Seed the policy corpus

Load the sample banking control matrix into pgvector so the RAG retriever has something to search:

```bash
uv run python scripts/seed_rag.py
```

### 5 — Submit a compliance run

```bash
curl -s -X POST http://localhost:8000/runs \
  -H "x-api-key: $API_KEY" \
  -F "pdf=@fixtures/regulations/your_circular.pdf" \
  -F "regulation_ref=RBI-MD-KYC-2016" \
  -F "domain=banking"
```

Response:
```json
{"run_id": "3fa85f64-...", "status": "pending"}
```

### 6 — Stream progress

```bash
curl -N http://localhost:8000/runs/RUN_ID/events \
  -H "x-api-key: $API_KEY"
```

You'll see SSE events as each node completes:

```
data: {"node": "ingest", "status": "running"}
data: {"node": "ingest", "status": "completed", "obligation_count": 28}
data: {"node": "retrieve_policies", "status": "running"}
...
data: {"node": "generate_report", "status": "awaiting_approval"}
```

The stream terminates when the run reaches `awaiting_approval`, `completed`, `rejected`, or `error`.

### 7 — Review and approve

Check the draft report status:

```bash
curl http://localhost:8000/runs/RUN_ID -H "x-api-key: $API_KEY"
```

Approve as-is:

```bash
curl -X POST http://localhost:8000/runs/RUN_ID/approve \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "edits": []}'
```

Approve with edits (override a gap status inline):

```bash
curl -X POST http://localhost:8000/runs/RUN_ID/approve \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "approved": true,
    "edits": [
      {"gap_id": "OBL-007", "status": "not_applicable"}
    ]
  }'
```

Reject (pipeline marks run as rejected and stops):

```bash
curl -X POST http://localhost:8000/runs/RUN_ID/approve \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"approved": false, "edits": []}'
```

### 8 — Fetch the final report

```bash
curl http://localhost:8000/runs/RUN_ID/report \
  -H "x-api-key: $API_KEY" | jq .
```

The response is a `ComplianceReport` JSON with per-obligation gap status, risk levels, recommendations, a summary, and a rendered markdown field.

---

## Running individual servers

You can run any service locally without Docker during development.

### API server

```bash
uv run uvicorn reglens.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Supervisor (LangGraph)

```bash
uv run python -m reglens.supervisor.server
```

### Ingestion agent (A2A, port 8001)

```bash
ADK_AGENT_PORT=8001 ADK_AGENT_NAME=document-ingestion \
  uv run python -m reglens.agents.ingestion.server
```

### Risk scorer agent (A2A, port 8002)

```bash
ADK_AGENT_PORT=8002 ADK_AGENT_NAME=risk-scorer \
  uv run python -m reglens.agents.risk_scorer.server
```

Each A2A agent exposes:
- `GET /.well-known/agent-card.json` — agent capabilities and skill manifest
- `GET /health` — liveness check
- `POST /jsonrpc` — JSON-RPC 2.0 method dispatch

---

## Development

```bash
# Install all dependencies including dev extras
uv sync --all-extras

# Run unit tests (no external services needed)
uv run pytest tests/unit -v

# Run with coverage
uv run pytest tests/unit --cov --cov-report=term-missing

# Run a single test file
uv run pytest tests/unit/test_nodes.py -v

# Lint and format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy src/reglens
```

Pre-commit hooks run ruff (lint + format) and mypy automatically on every commit:

```bash
uv run pre-commit install
```

---

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/runs` | Submit PDF + control matrix; returns `run_id` |
| `GET` | `/runs/{id}` | Poll run status |
| `GET` | `/runs/{id}/events` | SSE stream of node progress |
| `POST` | `/runs/{id}/approve` | Approve or reject the HITL gate |
| `GET` | `/runs/{id}/report` | Fetch the finalized `ComplianceReport` |
| `GET` | `/health` | Liveness check |

All endpoints except `/health` require the `x-api-key` header.

---

## Project layout

```
src/reglens/
├── api/           # FastAPI app, routers, middleware, deps
├── supervisor/    # LangGraph graph, nodes, state, pipeline, checkpoint
├── agents/
│   ├── ingestion/ # Gemini multimodal PDF → Obligation[]
│   ├── risk_scorer/ # Gemini risk scoring, A2A server
│   └── report/    # ComplianceReport builder + markdown renderer
├── a2a/           # JSON-RPC 2.0 server factory + httpx client
├── rag/           # pgvector store, embeddings, ingest
├── llm/           # Gemini (generation + embeddings) and Claude (structured)
├── schemas/       # Pydantic models — the contract between all agents
├── persistence/   # SQLAlchemy engine, ORM models, db_session
├── observability/ # structlog, OTel tracing, LangSmith
└── config.py      # pydantic-settings, single source of truth
```

See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the full architecture and phased build plan.
