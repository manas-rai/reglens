# reglens-ui

Next.js (App Router, TypeScript strict) demo UI for the RegLens compliance pipeline.

## Pages

- `/` — upload a regulation PDF and start a run
- `/runs/[id]` — live pipeline progress via SSE, auto-routes on terminal status
- `/runs/[id]/review` — HITL review of the draft report; approve (with optional gap-status overrides) or reject
- `/runs/[id]/report` — final compliance report

## Local dev

```bash
cp .env.example .env.local   # point at your local API
npm install
npm run dev
```

Talks to the FastAPI surface in `src/reglens/api`. Start the backend with `docker compose up` first, then visit http://localhost:3000.

The SSE endpoint passes the API key via query string (`?x-api-key=…`) because `EventSource` cannot set custom headers; the FastAPI auth dep accepts both header and query forms.
