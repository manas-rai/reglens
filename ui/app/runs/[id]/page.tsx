"use client";

import clsx from "clsx";
import { useRouter, useSearchParams } from "next/navigation";
import { use, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { StatusBadge } from "@/components/StatusBadge";
import { useToast } from "@/components/Toasts";
import {
  approveRun,
  eventsUrl,
  fetcher,
  type AuditEntry,
  type ComplianceReport,
  type CostResponse,
  type Edit,
  type GapResult,
  type RunStatus,
} from "@/lib/api";

interface PipelineEvent {
  node: string;
  status: string;
  detail?: string;
  ts: string;
}

const TERMINAL = new Set(["completed", "rejected", "error", "awaiting_approval"]);
const STATUSES = ["compliant", "partial_gap", "gap", "not_applicable"];
const LEVEL_ORDER = ["critical", "high", "medium", "low", "none"];

type Tab =
  | "overview"
  | "progress"
  | "gaps"
  | "risks"
  | "audit"
  | "costs"
  | "report"
  | "review";

const ALL_TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "progress", label: "Progress" },
  { id: "gaps", label: "Gaps" },
  { id: "risks", label: "Risks" },
  { id: "audit", label: "Audit" },
  { id: "costs", label: "Costs" },
  { id: "report", label: "Report" },
];

function parseTab(value: string | null): Tab {
  const candidates: Tab[] = [
    "overview",
    "progress",
    "gaps",
    "risks",
    "audit",
    "costs",
    "report",
    "review",
  ];
  return (candidates as string[]).includes(value ?? "")
    ? (value as Tab)
    : "overview";
}

export default function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = parseTab(searchParams.get("tab"));

  const { data: run, mutate: refetchRun } = useSWR<RunStatus>(
    `/runs/${id}`,
    fetcher,
    { refreshInterval: 5000 },
  );

  function setTab(next: Tab) {
    const sp = new URLSearchParams(searchParams.toString());
    sp.set("tab", next);
    router.replace(`/runs/${id}?${sp.toString()}`, { scroll: false });
  }

  const tabs = useMemo(() => {
    const list = [...ALL_TABS];
    if (run?.status === "awaiting_approval") {
      list.push({ id: "review", label: "Review" });
    }
    return list;
  }, [run?.status]);

  return (
    <>
      <div className="page-header">
        <h1>
          Run{" "}
          <span style={{ fontFamily: "monospace", fontSize: 14 }}>{id}</span>
        </h1>
        {run && <StatusBadge status={run.status} />}
      </div>

      <div className="tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={clsx("tab", tab === t.id && "active")}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab id={id} run={run} />}
      {tab === "progress" && (
        <ProgressTab id={id} runStatus={run?.status} onTerminal={() => refetchRun()} />
      )}
      {tab === "gaps" && <GapsTab id={id} />}
      {tab === "risks" && <RisksTab id={id} runStatus={run?.status} />}
      {tab === "audit" && <AuditTab id={id} />}
      {tab === "costs" && <CostsTab id={id} />}
      {tab === "report" && <ReportTab id={id} runStatus={run?.status} />}
      {tab === "review" && (
        <ReviewTab
          id={id}
          onSubmitted={(approved) => {
            refetchRun();
            setTab(approved ? "report" : "overview");
          }}
        />
      )}
    </>
  );
}

function OverviewTab({ id, run }: { id: string; run: RunStatus | undefined }) {
  if (!run) return <div className="muted">Loading…</div>;
  return (
    <div className="card">
      <div className="summary-grid">
        <Tile n={run.status.replace(/_/g, " ")} l="Status" />
        <Tile n={run.domain} l="Domain" />
        <Tile n={run.pdf_filename ?? "—"} l="File" />
        <Tile n={new Date(run.created_at).toLocaleString()} l="Created" />
      </div>
      {run.error_message && (
        <div className="error" style={{ marginTop: 16 }}>
          {run.error_message}
        </div>
      )}
      <p className="muted" style={{ marginTop: 16, marginBottom: 0 }}>
        Run ID: <code>{id}</code> · Updated{" "}
        {new Date(run.updated_at).toLocaleString()}
      </p>
    </div>
  );
}

function ProgressTab({
  id,
  runStatus,
  onTerminal,
}: {
  id: string;
  runStatus: string | undefined;
  onTerminal: () => void;
}) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);

  useEffect(() => {
    if (!runStatus || TERMINAL.has(runStatus)) return;

    const es = new EventSource(eventsUrl(id));
    es.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as Omit<PipelineEvent, "ts">;
        const evt: PipelineEvent = {
          ...data,
          ts: new Date().toLocaleTimeString(),
        };
        setEvents((prev) => [...prev, evt]);
        if (TERMINAL.has(data.status)) {
          es.close();
          onTerminal();
        }
      } catch (e) {
        console.error("event parse", e);
      }
    };
    es.onerror = () => {
      es.close();
      setStreamError("Event stream closed.");
      onTerminal();
    };
    return () => es.close();
  }, [id, runStatus, onTerminal]);

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Pipeline events</h2>
      {runStatus && TERMINAL.has(runStatus) && (
        <div className="muted" style={{ marginBottom: 12 }}>
          Run is {runStatus.replace(/_/g, " ")}. Live stream not available;
          check Audit tab for the full log.
        </div>
      )}
      {streamError && (
        <div className="muted" style={{ marginBottom: 12 }}>
          {streamError}
        </div>
      )}
      <div className="event-log">
        {events.length === 0 ? (
          <div className="muted">
            {runStatus && !TERMINAL.has(runStatus)
              ? "Waiting for first event…"
              : "No live events."}
          </div>
        ) : (
          events.map((e, i) => (
            <div className="event-row" key={i}>
              <span>
                <strong>{e.node}</strong>
                {e.detail ? ` — ${e.detail}` : ""}
              </span>
              <span className="muted">
                {e.status} · {e.ts}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function GapsTab({ id }: { id: string }) {
  const { data, error, isLoading } = useSWR<{ items: GapResult[] }>(
    `/runs/${id}/gaps`,
    fetcher,
  );
  if (isLoading) return <div className="muted">Loading gaps…</div>;
  if (error)
    return (
      <div className="empty">
        Gap analysis not yet available for this run.
      </div>
    );
  const items = data?.items ?? [];
  if (items.length === 0) return <div className="empty">No gaps yet.</div>;
  return (
    <div className="card">
      <table className="risk-table">
        <thead>
          <tr>
            <th>Obligation</th>
            <th>Status</th>
            <th>Gap / recommendation</th>
          </tr>
        </thead>
        <tbody>
          {items.map((g) => (
            <tr key={g.obligation.id}>
              <td>
                <strong>{g.obligation.id}</strong>
                <div className="muted">{g.obligation.clause}</div>
                <div style={{ fontSize: 12, marginTop: 4 }}>
                  {g.obligation.text}
                </div>
              </td>
              <td>{g.status.replace(/_/g, " ")}</td>
              <td style={{ fontSize: 13 }}>
                {g.gap_description && (
                  <div>
                    <strong>Gap:</strong> {g.gap_description}
                  </div>
                )}
                {g.recommendation && (
                  <div style={{ marginTop: 4 }}>
                    <strong>Recommendation:</strong> {g.recommendation}
                  </div>
                )}
                <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                  {g.reasoning}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function useDraftOrReport(id: string, runStatus: string | undefined) {
  const key =
    runStatus === "completed"
      ? `/runs/${id}/report`
      : runStatus === "awaiting_approval"
        ? `/runs/${id}/draft`
        : null;
  const swr = useSWR<ComplianceReport | { draft_report: ComplianceReport }>(
    key,
    fetcher,
  );
  const report: ComplianceReport | null = swr.data
    ? "draft_report" in swr.data
      ? swr.data.draft_report
      : (swr.data as ComplianceReport)
    : null;
  return { report, error: swr.error, isLoading: swr.isLoading };
}

function RisksTab({
  id,
  runStatus,
}: {
  id: string;
  runStatus: string | undefined;
}) {
  const { report, error, isLoading } = useDraftOrReport(id, runStatus);
  if (!runStatus || !["awaiting_approval", "completed"].includes(runStatus))
    return (
      <div className="empty">
        Risk scores appear once gap analysis completes.
      </div>
    );
  if (isLoading) return <div className="muted">Loading…</div>;
  if (error) return <div className="error">{String(error.message)}</div>;
  if (!report) return <div className="muted">No report data.</div>;
  const sorted = [...report.risk_scores].sort(
    (a, b) =>
      LEVEL_ORDER.indexOf(a.risk_level) - LEVEL_ORDER.indexOf(b.risk_level),
  );
  return (
    <>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Risk distribution</h2>
        <div className="summary-grid">
          {LEVEL_ORDER.map((lvl) => (
            <Tile
              key={lvl}
              n={report.summary.by_risk_level[lvl] ?? 0}
              l={lvl}
            />
          ))}
        </div>
      </div>
      <div className="card">
        <table className="risk-table">
          <thead>
            <tr>
              <th>Obligation</th>
              <th>Risk</th>
              <th>Score</th>
              <th>Justification</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((rs) => (
              <tr key={rs.gap_result.obligation.id}>
                <td>
                  <strong>{rs.gap_result.obligation.id}</strong>
                  <div className="muted">{rs.gap_result.obligation.clause}</div>
                </td>
                <td className={`risk-${rs.risk_level}`}>
                  {rs.risk_level.toUpperCase()}
                </td>
                <td>{rs.score.toFixed(1)}</td>
                <td style={{ fontSize: 12 }}>{rs.justification}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function AuditTab({ id }: { id: string }) {
  const { data, error, isLoading } = useSWR<{ items: AuditEntry[] }>(
    `/runs/${id}/audit`,
    fetcher,
  );
  if (isLoading) return <div className="muted">Loading audit log…</div>;
  if (error) return <div className="error">{String(error.message)}</div>;
  const items = data?.items ?? [];
  if (items.length === 0) return <div className="empty">No audit entries.</div>;
  return (
    <div className="card">
      <table className="risk-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Node</th>
            <th>Actor</th>
            <th>Payload</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={row.id}>
              <td className="muted">
                {new Date(row.created_at).toLocaleTimeString()}
              </td>
              <td>{row.node}</td>
              <td>{row.actor}</td>
              <td>
                <pre
                  style={{
                    margin: 0,
                    fontSize: 11,
                    maxWidth: 480,
                    overflow: "auto",
                  }}
                >
                  {row.payload ? JSON.stringify(row.payload, null, 2) : "—"}
                </pre>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CostsTab({ id }: { id: string }) {
  const { data, error, isLoading } = useSWR<CostResponse>(
    `/runs/${id}/costs`,
    fetcher,
  );
  if (isLoading) return <div className="muted">Loading costs…</div>;
  if (error) return <div className="error">{String(error.message)}</div>;
  if (!data || data.items.length === 0)
    return <div className="empty">No cost records yet.</div>;
  return (
    <>
      <div className="card">
        <div className="summary-grid">
          <Tile n={`$${data.total_cost_usd.toFixed(4)}`} l="Total cost" />
          <Tile n={data.total_prompt_tokens} l="Prompt tokens" />
          <Tile n={data.total_completion_tokens} l="Completion tokens" />
          <Tile n={data.items.length} l="LLM calls" />
        </div>
      </div>
      <div className="card">
        <table className="risk-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Agent</th>
              <th>Model</th>
              <th>Prompt</th>
              <th>Completion</th>
              <th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((c) => (
              <tr key={c.id}>
                <td className="muted">
                  {new Date(c.created_at).toLocaleTimeString()}
                </td>
                <td>{c.agent}</td>
                <td className="muted">{c.model}</td>
                <td>{c.prompt_tokens}</td>
                <td>{c.completion_tokens}</td>
                <td>${c.cost_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ReportTab({
  id,
  runStatus,
}: {
  id: string;
  runStatus: string | undefined;
}) {
  const { report, error, isLoading } = useDraftOrReport(id, runStatus);
  if (runStatus !== "completed")
    return (
      <div className="empty">
        Final report appears once the run is approved and completed.
      </div>
    );
  if (isLoading) return <div className="muted">Loading report…</div>;
  if (error) return <div className="error">{String(error.message)}</div>;
  if (!report) return <div className="muted">No report.</div>;
  return (
    <>
      <div className="card">
        <p style={{ margin: 0 }}>
          {report.regulation_ref} · {report.domain} · generated{" "}
          {new Date(report.generated_at).toLocaleString()}
        </p>
      </div>
      <div className="card">
        <div className="summary-grid">
          <Tile n={report.summary.compliant} l="Compliant" />
          <Tile n={report.summary.partial_gap} l="Partial gap" />
          <Tile n={report.summary.gap} l="Gap" />
          <Tile n={report.summary.not_applicable} l="N/A" />
        </div>
      </div>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Markdown</h2>
        <pre
          style={{
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontFamily: "inherit",
            fontSize: 13,
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          {report.markdown}
        </pre>
      </div>
    </>
  );
}

function ReviewTab({
  id,
  onSubmitted,
}: {
  id: string;
  onSubmitted: (approved: boolean) => void;
}) {
  const toast = useToast();
  const { report, error, isLoading } = useDraftOrReport(id, "awaiting_approval");
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function setOverride(obligationId: string, value: string, current: string) {
    setOverrides((prev) => {
      const next = { ...prev };
      if (value === current) delete next[obligationId];
      else next[obligationId] = value;
      return next;
    });
  }

  async function submit(approved: boolean) {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const edits: Edit[] = approved
        ? Object.entries(overrides).map(([obligation_id, status]) => ({
            obligation_id,
            status,
          }))
        : [];
      await approveRun(id, approved, edits);
      toast.push(
        "success",
        approved
          ? `Approved${edits.length > 0 ? ` with ${edits.length} edit(s)` : ""}`
          : "Run rejected",
      );
      onSubmitted(approved);
    } catch (e) {
      const msg = String(e);
      setSubmitError(msg);
      toast.push("error", msg);
      setSubmitting(false);
    }
  }

  if (isLoading) return <div className="muted">Loading draft…</div>;
  if (error) return <div className="error">{String(error.message)}</div>;
  if (!report) return <div className="muted">No draft.</div>;

  return (
    <>
      <div className="card">
        <p style={{ margin: 0 }}>
          {report.regulation_ref} · {report.domain} ·{" "}
          {report.summary.total_obligations} obligations
        </p>
      </div>
      <div className="card">
        <div className="summary-grid">
          <Tile n={report.summary.compliant} l="Compliant" />
          <Tile n={report.summary.partial_gap} l="Partial gap" />
          <Tile n={report.summary.gap} l="Gap" />
          <Tile n={report.summary.not_applicable} l="N/A" />
        </div>
      </div>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Findings</h2>
        <table className="risk-table">
          <thead>
            <tr>
              <th>Obligation</th>
              <th>Risk</th>
              <th>Status</th>
              <th>Override</th>
            </tr>
          </thead>
          <tbody>
            {report.risk_scores.map((rs) => {
              const obligationId = rs.gap_result.obligation.id;
              const current = rs.gap_result.status;
              const override = overrides[obligationId];
              return (
                <tr key={obligationId}>
                  <td>
                    <strong>{obligationId}</strong>
                    <div className="muted">{rs.gap_result.obligation.clause}</div>
                  </td>
                  <td className={`risk-${rs.risk_level}`}>
                    {rs.risk_level} ({rs.score.toFixed(1)})
                  </td>
                  <td>{current.replace(/_/g, " ")}</td>
                  <td>
                    <select
                      value={override ?? current}
                      onChange={(e) =>
                        setOverride(obligationId, e.target.value, current)
                      }
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {s.replace(/_/g, " ")}
                          {s === current ? " (current)" : ""}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {submitError && <div className="error">{submitError}</div>}
      <div className="actions">
        <button onClick={() => submit(true)} disabled={submitting}>
          Approve
          {Object.keys(overrides).length > 0
            ? ` with ${Object.keys(overrides).length} edit(s)`
            : ""}
        </button>
        <button
          className="danger"
          onClick={() => submit(false)}
          disabled={submitting}
        >
          Reject
        </button>
      </div>
    </>
  );
}

function Tile({ n, l }: { n: number | string; l: string }) {
  return (
    <div className="summary-tile">
      <span className="num">{n}</span>
      <span className="lbl">{l}</span>
    </div>
  );
}
