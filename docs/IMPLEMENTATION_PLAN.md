# RegLens — Production Build Plan

> This document is the source of truth for the RegLens implementation plan. It is checked into the repo so it survives across tools, machines, and collaborators. Update it via PRs when scope or architecture changes.

## Context

RegLens is a greenfield project. The repo currently contains only `README.md`, `LICENSE`, a Python-flavored `.gitignore`, and a `CLAUDE.md` placeholder — no source code yet.

The product: a multi-agent system that ingests a regulatory PDF + an organization's control matrix and produces a structured compliance-gap report (per-obligation classification + risk severity + recommendation), with a human-in-the-loop approval gate before finalization. The design intentionally splits work across **LangGraph** (orchestration, gap analysis, report + HITL) and **Google ADK** (multimodal PDF ingestion, risk scoring) connected by the **A2A protocol**, so the seam between frameworks is real and observable, not academic.

**Why this matters now:** regulated organizations burn weeks of senior-compliance time per circular doing this manually. The output is also stale by definition. There is no widely available open-source system that does this end-to-end with structured evaluations.

**Foundational decisions:**
- **Build order:** vertical MVP first (banking domain, one regulation → one report end-to-end), then harden, then multi-domain.
- **Deployment:** cloud-agnostic containers with **AWS** as the documented reference target (not GCP — Gemini works via AI Studio API key from anywhere; Cloud Trace is replaceable by OTel exporters).
- **LLMs:** Gemini via AI Studio API key (ADK agents) + Anthropic API direct (LangGraph agents). No Bedrock for now.
- **HITL surface:** FastAPI only — `POST /runs`, `GET /runs/{id}`, `POST /runs/{id}/approve`. No web UI in MVP.

---

## Architecture

```
                ┌─────────────────────────────────────────────┐
                │  FastAPI (reglens-api)                       │
                │  POST /runs · GET /runs/{id} · /approve · SSE│
                └───────────────┬─────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────┐
        │  LangGraph Supervisor  (reglens-langgraph)         │
        │  StateGraph + PostgresSaver checkpoint             │
        │  Nodes: ingest → knowledge → gap (fan-out) →       │
        │         risk (fan-out) → report → HITL interrupt   │
        └───┬───────────────┬───────────────┬───────────────┘
            │               │               │
       A2A  │ JSON-RPC 2.0  │               │ in-process
       HTTP │               │               │
            ▼               ▼               ▼
   ┌─────────────┐   ┌─────────────┐   ┌─────────────────────┐
   │ ADK         │   │ ADK         │   │ LangGraph nodes:    │
   │ Ingestion   │   │ Risk Scorer │   │  - Knowledge (RAG)  │
   │ (Gemini     │   │ (Gemini)    │   │  - Gap Analyzer     │
   │  multimodal)│   │             │   │    (Claude)         │
   └─────────────┘   └─────────────┘   │  - Report Generator │
                                       │    (Claude)         │
                                       └─────────────────────┘

   Persistence: Postgres (LangGraph checkpoints, run metadata,
                pgvector for policy embeddings, audit log)
   Tracing:     LangSmith (LangGraph) + OTel (everything else,
                console exporter in dev, X-Ray/CloudWatch in AWS)
```

Key invariants:
- **The A2A seam is the only network boundary inside the system.** LangGraph and ADK never share process. Each ADK agent runs as its own A2A server with an Agent Card at `/.well-known/agent-card.json`.
- **All state lives in Postgres.** A run is fully resumable from any node after crash, including across the HITL interrupt.
- **All LLM outputs are Pydantic-validated.** No free-text JSON parsing.

---

## Repository Layout

```
reglens/
├── pyproject.toml                # uv-managed, Python 3.11+
├── uv.lock
├── docker-compose.yml             # postgres+pgvector, langgraph, adk-ingest, adk-risk, api
├── .env.example
├── docker/
│   ├── langgraph.Dockerfile
│   ├── adk.Dockerfile             # shared image for ADK agents, entrypoint picks agent
│   └── api.Dockerfile
├── src/reglens/
│   ├── config.py                  # pydantic-settings, env-driven
│   ├── schemas/                   # Pydantic models — the contract layer
│   │   ├── obligation.py          # Obligation, ObligationType
│   │   ├── policy.py              # Policy, PolicyMatch
│   │   ├── gap.py                 # GapResult, GapStatus
│   │   ├── risk.py                # RiskScore, RiskLevel
│   │   └── report.py              # ComplianceReport
│   ├── supervisor/
│   │   ├── graph.py               # build_supervisor_graph()
│   │   ├── state.py               # SupervisorState (TypedDict)
│   │   ├── nodes.py               # per-step node functions
│   │   └── checkpoint.py          # PostgresSaver wiring
│   ├── agents/
│   │   ├── ingestion/             # ADK + Gemini, exposed via A2A
│   │   │   ├── agent.py
│   │   │   ├── prompts.py
│   │   │   └── server.py          # A2A server entrypoint
│   │   ├── knowledge/             # in-process LangGraph node + RAG
│   │   │   ├── retriever.py
│   │   │   └── node.py
│   │   ├── gap_analyzer/          # in-process LangGraph node, Claude
│   │   │   ├── analyzer.py
│   │   │   ├── prompts.py
│   │   │   └── node.py            # uses Send() for fan-out
│   │   ├── risk_scorer/           # ADK + Gemini, exposed via A2A
│   │   │   ├── agent.py
│   │   │   ├── prompts.py
│   │   │   └── server.py
│   │   └── report/                # in-process LangGraph node
│   │       ├── renderer.py        # JSON + markdown
│   │       └── node.py            # contains interrupt()
│   ├── a2a/
│   │   ├── card.py                # AgentCard pydantic model
│   │   ├── server.py              # FastAPI-based JSON-RPC 2.0 wrapper
│   │   ├── client.py              # HTTPX-based client w/ tenacity retries
│   │   └── discovery.py           # fetch + cache Agent Cards
│   ├── rag/
│   │   ├── store.py               # pgvector via SQLAlchemy
│   │   ├── ingest.py              # control matrix YAML/JSON → embeddings
│   │   └── embeddings.py          # Gemini or Voyage embeddings
│   ├── api/
│   │   ├── main.py                # FastAPI app factory
│   │   ├── routers/
│   │   │   ├── runs.py            # POST /runs, GET /runs/{id}, /approve, /events
│   │   │   └── health.py
│   │   ├── deps.py                # DB session, auth, settings injection
│   │   └── middleware/
│   │       ├── auth.py            # API key auth
│   │       ├── request_id.py
│   │       └── ratelimit.py       # slowapi
│   ├── llm/
│   │   ├── gemini.py              # AI Studio client
│   │   └── claude.py              # Anthropic SDK client
│   ├── observability/
│   │   ├── tracing.py             # OTel SDK setup, A2A boundary spans
│   │   ├── logging.py             # structlog JSON
│   │   ├── metrics.py             # prometheus + cost counters
│   │   └── langsmith.py           # LangSmith client setup
│   ├── persistence/
│   │   ├── db.py                  # SQLAlchemy engine + session
│   │   ├── models.py              # ORM: Run, AuditLog, CostRecord
│   │   └── migrations/            # alembic
│   └── domain/                    # domain-specific configs (Phase 4)
│       └── banking/
│           ├── risk_rubric.yaml
│           └── matrix_schema.py
├── tests/
│   ├── unit/
│   ├── integration/               # supervisor graph with stub A2A
│   └── e2e/                       # docker-compose-driven
├── evals/
│   ├── datasets/                  # annotated PDFs, labeled pairs, scenarios
│   ├── component/                 # per-agent eval scripts
│   └── end_to_end/                # full report grading
├── fixtures/
│   ├── regulations/               # sample RBI circular PDF
│   └── control_matrices/          # synthetic banking matrix YAML
├── scripts/
│   ├── seed_rag.py                # load fixtures into pgvector
│   └── run_smoke.py
├── infra/
│   └── aws/                       # Terraform (Phase 5)
└── docs/
    ├── IMPLEMENTATION_PLAN.md      # this file
    ├── architecture.md
    ├── a2a-protocol.md
    ├── deployment-aws.md
    └── runbook.md
```

---

## Phased Plan

### Phase 0 — Foundation (1 PR)

- `uv init` → `pyproject.toml`, `src/reglens/` layout, Python 3.11+
- Ruff (format + lint), mypy strict on `src/`, pre-commit hooks
- pytest + pytest-asyncio; one passing smoke test
- `docker-compose.yml`: `postgres` (with `pgvector` extension installed via image `pgvector/pgvector:pg18`), `reglens-api`, `reglens-langgraph`, `reglens-adk-ingest`, `reglens-adk-risk`
- `.env.example` with all keys; `config.py` using `pydantic-settings`
- Structured JSON logging (structlog) + OTel SDK with console exporter
- GitHub Actions: ruff, mypy, pytest on PR
- Alembic initialized; baseline migration for `runs`, `audit_log`, `cost_records`, pgvector tables

### Phase 1 — Vertical MVP (banking, end-to-end)

**Goal:** `docker compose up` → `POST /runs` with an RBI circular PDF + synthetic banking matrix → SSE progress stream → HITL interrupt → `POST /approve` → final `ComplianceReport` JSON + markdown. At least the planted gaps (25–30) are detected.

Critical files (all new):

1. **Schemas** (`src/reglens/schemas/*.py`) — Pydantic v2 models for `Obligation`, `Policy`, `PolicyMatch`, `GapResult`, `RiskScore`, `ComplianceReport`. These are the contract for every agent.

2. **LangGraph Supervisor** (`src/reglens/supervisor/graph.py`, `state.py`, `nodes.py`):
   - `SupervisorState` TypedDict: `run_id`, `pdf_uri`, `matrix_uri`, `obligations`, `matches`, `gaps`, `risks`, `report`, `error`.
   - Nodes: `ingest` (A2A call) → `retrieve_policies` (in-process RAG) → `analyze_gaps` (fan-out via `Send`) → `score_risks` (fan-out, A2A) → `generate_report` (in-process, calls `interrupt()` for HITL).
   - `PostgresSaver` checkpointer wired via `from langgraph.checkpoint.postgres import PostgresSaver`.

3. **A2A layer** (`src/reglens/a2a/`):
   - `card.py`: `AgentCard` Pydantic model matching A2A spec (name, description, url, capabilities, skills, version).
   - `server.py`: a small FastAPI factory that mounts JSON-RPC 2.0 at `/jsonrpc` and the agent card at `/.well-known/agent-card.json`. Handles `message/send` and `tasks/get` per A2A spec.
   - `client.py`: httpx client with tenacity-backed retries (exponential backoff, max 3 attempts, retry on 5xx / connection errors), OTel span around every call recording payload sizes and round-trip latency. **This is where the cross-framework boundary is observable.**
   - `discovery.py`: fetch + LRU-cache Agent Cards on startup.

4. **ADK Document Ingestion Agent** (`src/reglens/agents/ingestion/`):
   - Uses `google.adk` with Gemini 2.5 Pro (multimodal). Input: PDF bytes. Output: `list[Obligation]` validated against the Pydantic schema.
   - System prompt enforces structured extraction with explicit clause/section/page references and obligation type classification.
   - `server.py` wraps the agent in the A2A server. Runs on its own container/port.

5. **Knowledge Agent / RAG** (`src/reglens/rag/`, `src/reglens/agents/knowledge/`):
   - `store.py`: pgvector via SQLAlchemy. Table `policies` with columns `id, domain, policy_id, section, text, embedding (vector)`.
   - `ingest.py`: load control matrix YAML, chunk by policy section, embed via Gemini `text-embedding-004`, upsert.
   - `node.py`: for each obligation, run semantic search (top-K=5), return `list[PolicyMatch]` with relevance scores.

6. **Gap Analyzer Agent** (`src/reglens/agents/gap_analyzer/`):
   - In-process LangGraph node, fan-out via `Send()` so each `(obligation, matches)` pair runs concurrently.
   - Anthropic Claude (claude-sonnet-4-6) with `response_model` via instructor or native tool-use to enforce `GapResult` schema.
   - Classifies COMPLIANT / PARTIAL GAP / GAP / NOT APPLICABLE with reasoning.

7. **ADK Risk Scorer Agent** (`src/reglens/agents/risk_scorer/`):
   - Gemini-backed ADK agent, exposed via A2A. Input: `GapResult` + domain risk rubric. Output: `RiskScore` (CRITICAL/HIGH/MEDIUM/LOW + justification).
   - Banking risk rubric loaded from `src/reglens/domain/banking/risk_rubric.yaml`.

8. **Report Generator + HITL** (`src/reglens/agents/report/`):
   - Aggregates `GapResult` + `RiskScore` into a `ComplianceReport`.
   - Renders JSON + markdown; PDF rendering via `weasyprint` (deferred — markdown is enough for MVP).
   - Calls `interrupt({"draft": report})` to pause; `POST /approve` resumes with `Command(resume={"approved": True, "edits": [...]})`.

9. **FastAPI service** (`src/reglens/api/`):
   - `POST /runs` (multipart upload: PDF + matrix YAML) → returns `run_id`, kicks off graph asynchronously.
   - `GET /runs/{id}` → status from PostgresSaver state.
   - `GET /runs/{id}/events` → SSE stream of node transitions.
   - `POST /runs/{id}/approve` → body: `{"approved": bool, "edits": [...]}`; resumes graph.
   - `GET /runs/{id}/report` → final JSON + markdown.
   - API-key middleware (single static key from env for MVP, pluggable later).

10. **Fixtures**:
    - One real RBI circular PDF in `fixtures/regulations/`.
    - Synthetic banking control matrix (YAML) with 25–30 deliberate gaps planted against specific clauses.
    - `scripts/seed_rag.py` to load the matrix into pgvector on `docker compose up`.

11. **Smoke test** (`tests/e2e/test_smoke.py`): spins up compose, runs a full pipeline, asserts run reaches HITL gate; approves; asserts at least N planted gaps are present in final report.

### Phase 2 — Hardening + Evaluation

- LangSmith tracing on every LangGraph node (env-driven; no-op if `LANGSMITH_API_KEY` unset).
- OTel spans on every A2A call recording: request bytes, response bytes, status, attempt count, model used.
- Retry policy formalized: tenacity decorators on A2A client and LLM client modules. Idempotency keys (`run_id` + `node` + `obligation_id`) so retries don't duplicate work.
- Auth: API-key header middleware (already in MVP); add audit log entry on every state transition.
- Rate limiting via `slowapi` on the API layer.
- Error taxonomy: `ReglensError` base, subclasses for `IngestionError`, `A2ATransportError`, `LLMValidationError`, etc. Mapped to HTTP status codes via FastAPI exception handlers.

**Evaluation suites** (`evals/`):
- `component/ingestion_eval.py`: precision/recall against 10–15 annotated PDFs (`evals/datasets/ingestion/`).
- `component/rag_eval.py`: hit@k and MRR on labeled (obligation → policy) pairs.
- `component/gap_eval.py`: classification accuracy with confusion matrix, F1 per class.
- `component/risk_eval.py`: weighted accuracy against expert labels.
- `component/routing_eval.py`: replay supervisor traces, check node sequence against expected.
- `end_to_end/scenarios.py`: 10 scenarios; metrics — gap precision/recall/F1, severity accuracy, p50/p95 latency, token cost per report.
- LangSmith evaluator functions registered for LLM-as-judge metrics.

### Phase 3 — Observability + Cost Controls

- Prometheus metrics endpoint via `prometheus-fastapi-instrumentator`.
- Per-agent, per-model token cost captured in `cost_records` table on every LLM call; emitted as OTel metrics.
- LangSmith dashboard config (saved views, organization conventions documented in `docs/runbook.md`).
- Grafana dashboard JSON checked into `infra/grafana/` (token cost, gap detection rate, false-positive rate, p50/p95 latency).
- Audit log: every state transition with timestamp, actor (system vs. human reviewer), payload diff.

### Phase 4 — Multi-Domain

- Healthcare: NABH/ICMR risk rubric YAML, healthcare matrix schema, 2 eval scenarios.
- SaaS: GDPR/SOC2 risk rubric YAML, SaaS matrix schema, 2 eval scenarios.
- All swappable via `domain` config field on the run; **no agent code changes**.

### Phase 5 — AWS Reference Deployment

- `infra/aws/` Terraform: VPC, ECS Fargate services (api, langgraph, adk-ingest, adk-risk), RDS Postgres 16 with pgvector, Secrets Manager (API keys), ALB with path-based routing, CloudWatch Logs, X-Ray.
- OTel collector sidecar exporting to X-Ray + CloudWatch.
- ECR build/push GitHub Action.
- `docs/deployment-aws.md` runbook.

---

## Key Reuse / Library Choices

- **A2A:** Roll our own minimal JSON-RPC 2.0 server/client (the official A2A SDK is young; building a thin layer is more honest and shows the protocol explicitly — which is half the architectural point). Validate Agent Cards against the published JSON schema from a2aproject.org.
- **LangGraph:** v1.2+, `PostgresSaver` checkpointer, `Send` for fan-out, `interrupt`/`Command` for HITL.
- **ADK:** `google.adk` with Gemini 2.5 Pro for ingestion, Gemini 2.5 Flash for risk scoring.
- **LLM clients:** `anthropic` SDK direct (Claude), `google-genai` (Gemini). Avoid LiteLLM/LangChain provider abstractions — they obscure failures.
- **Validation:** Pydantic v2 everywhere. Use `instructor` for Claude structured output, native tool-use for Gemini.
- **DB:** SQLAlchemy 2.x + Alembic + `pgvector` (`pgvector-python`).
- **HTTP:** httpx (async) for A2A client and LLM clients.
- **Tracing:** `opentelemetry-sdk` + `opentelemetry-instrumentation-fastapi`/`-httpx` + LangSmith.
- **Logging:** structlog with JSON renderer.

---

## Verification

End-to-end MVP checks (Phase 1 acceptance):
1. `docker compose up` cleanly starts all services. Health endpoints green.
2. `scripts/seed_rag.py` loads the synthetic banking matrix into pgvector.
3. `curl -X POST /runs -F pdf=@fixtures/regulations/rbi_*.pdf -F matrix=@fixtures/control_matrices/banking.yaml -H "x-api-key: ..."` returns a `run_id`.
4. `curl /runs/{id}/events` streams progress through `ingest → retrieve → analyze → score → report`.
5. Run pauses at `report` node (HITL interrupt). `GET /runs/{id}` shows status `awaiting_approval` with the draft report.
6. `curl -X POST /runs/{id}/approve -d '{"approved": true}'` resumes.
7. `GET /runs/{id}/report` returns a `ComplianceReport` JSON containing at least the planted gaps from the synthetic matrix.
8. LangSmith trace shows full node-by-node execution. OTel console exporter shows A2A spans with payload sizes and latencies.

Resilience checks (Phase 2):
- `docker kill reglens-adk-risk` mid-run; verify supervisor retries via A2A client, then checkpoint-resumes after container restart, without re-doing completed work.
- Approve with edits (`{"approved": true, "edits": [{"gap_id": "...", "status": "NOT_APPLICABLE"}]}`); verify final report reflects edits and audit log records the diff.

Eval checks (Phase 2):
- `uv run python -m evals.end_to_end.scenarios` produces metrics report; baseline thresholds: gap recall ≥ 0.85, gap precision ≥ 0.75, severity accuracy ≥ 0.70 against ground truth.

AWS deployment check (Phase 5):
- `terraform apply` → smoke-test script hits ALB endpoint with the same fixtures and produces the same report shape.

---

## Out of Scope

- Web UI (deferred; API is the surface).
- Multi-tenancy (single-tenant API-key auth in MVP; org/user model later).
- Real customer data ingestion connectors (e.g., pulling policies from a live GRC platform).
- AWS Bedrock for Claude (uses Anthropic API direct).
- Vertex AI for Gemini (uses AI Studio API key).
- PDF rendering of final report (markdown is enough; weasyprint can be added trivially later).
