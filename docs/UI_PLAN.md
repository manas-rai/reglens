# UI Plan — Full-Fledged Demo Frontend

Status: in progress (PR 1 of 4 — backend list/read endpoints)

The initial demo UI (PR #7) covered only the happy path: upload → progress → review → report, with no way to find a run after closing the tab. This plan extends both backend and frontend to a production-quality demo surface covering every observable artifact of the pipeline.

## Backend endpoints to add

All read-only, all guarded by `require_api_key`. No new tables.

| Endpoint | Purpose |
|---|---|
| `GET /runs?status&domain&limit&offset` | Paginated run list with filters |
| `GET /runs/{id}/audit` | Read `audit_log` rows for the run |
| `GET /runs/{id}/costs` | Read `cost_records` rows for the run |
| `GET /runs/{id}/gaps` | Gap results from graph state (works mid-run, unlike `/report`) |
| `GET /policies?domain&q&limit&offset` | Browse seeded policy corpus |
| `GET /policies/{id}` | Policy detail |
| `GET /stats` | Aggregates: total runs, by status, total cost |

## UI pages

```
/                              Dashboard — KPI tiles + recent runs + status chart
/runs                          List — filters (status, domain, date), pagination, search by id
/runs/new                      Upload (current `/` content moves here)
/runs/[id]                     Detail shell with tabs:
  ├ overview                   Status, metadata, timeline, summary tiles
  ├ progress                   SSE event log (live) + historical events from audit
  ├ obligations                Extracted obligations table
  ├ gaps                       Gap classifications with reasoning, filter by status
  ├ risks                      Risk scores sorted by severity
  ├ audit                      Full audit log (actor, node, payload, ts)
  ├ costs                      Per-node cost breakdown, tokens, model
  └ report                     Final report (md + structured), download button
/runs/[id]/review              HITL — full diff view, bulk status edits, reject with reason
/policies                      Browse corpus, filter by domain, search
/policies/[id]                 Policy detail
/settings                      API key entry (localStorage), backend URL, theme
```

## Component additions

- Shared layout: sidebar nav (Dashboard, Runs, Policies, Settings) + topbar
- `lucide-react` icons, `swr` for data fetching/caching, `clsx`
- Primitives: `Tabs`, `Table`, `Drawer`, `EmptyState`
- Toast notifications for action feedback

## Auth UX

Replace env-baked `NEXT_PUBLIC_API_KEY` with a Settings page that writes the key to `localStorage`. A fetch hook injects it into every request. First-visit redirect → `/settings` if no key set.

## Delivery

| PR | Branch | Scope |
|----|--------|-------|
| 1 | `api/list-and-read-endpoints` | All seven new backend endpoints + tests |
| 2 | `ui/shell-and-runs-list` | Sidebar/topbar shell, dashboard, `/runs` list, `/runs/new`, settings page with key storage |
| 3 | `ui/run-detail-tabs` | Tabbed detail page (overview / progress / obligations / gaps / risks / audit / costs / report), bulk-edit review |
| 4 | `ui/policies-and-polish` | Policies browser, toasts, empty states, loading skeletons, keyboard shortcuts |

Each PR ships green CI (ruff, mypy, pytest, typecheck, next build) and is independently mergeable.

## Out of scope

- User accounts / RBAC — still single API key
- Real-time collaboration on review
- Editing obligations / re-running steps
- Writing back to the policy corpus
