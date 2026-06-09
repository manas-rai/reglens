"use client";

import Link from "next/link";
import useSWR from "swr";
import { StatusBadge } from "@/components/StatusBadge";
import {
  fetcher,
  type RunListResponse,
  type Stats,
} from "@/lib/api";

export default function DashboardPage() {
  const stats = useSWR<Stats>("/stats", fetcher, { refreshInterval: 5000 });
  const recent = useSWR<RunListResponse>(
    "/runs?limit=5&offset=0",
    fetcher,
    { refreshInterval: 5000 },
  );

  return (
    <>
      <div className="page-header">
        <h1>Dashboard</h1>
        <Link href="/runs/new">
          <button>New run</button>
        </Link>
      </div>

      {stats.error && (
        <div className="error">
          Cannot reach API: {String(stats.error.message)}. Check{" "}
          <Link href="/settings">Settings</Link>.
        </div>
      )}

      <div className="kpi-grid">
        <Kpi label="Total runs" value={stats.data?.total_runs ?? "—"} />
        <Kpi
          label="Completed"
          value={stats.data?.by_status?.completed ?? 0}
        />
        <Kpi
          label="Awaiting approval"
          value={stats.data?.by_status?.awaiting_approval ?? 0}
        />
        <Kpi
          label="Total cost"
          value={
            stats.data
              ? `$${stats.data.total_cost_usd.toFixed(4)}`
              : "—"
          }
        />
      </div>

      <div className="card">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 12,
          }}
        >
          <h2 style={{ margin: 0 }}>Recent runs</h2>
          <Link href="/runs" style={{ fontSize: 13 }}>
            View all →
          </Link>
        </div>
        <RunsTable rows={recent.data?.items ?? []} loading={recent.isLoading} />
      </div>
    </>
  );
}

function Kpi({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

function RunsTable({
  rows,
  loading,
}: {
  rows: { run_id: string; status: string; domain: string; pdf_filename: string | null; created_at: string }[];
  loading: boolean;
}) {
  if (loading) return <div className="muted">Loading…</div>;
  if (rows.length === 0)
    return (
      <div className="empty">
        No runs yet. <Link href="/runs/new">Start one →</Link>
      </div>
    );
  return (
    <table className="risk-table">
      <thead>
        <tr>
          <th>Run</th>
          <th>Status</th>
          <th>Domain</th>
          <th>File</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.run_id}>
            <td>
              <Link href={`/runs/${r.run_id}`} className="run-row-link">
                {r.run_id.slice(0, 8)}…
              </Link>
            </td>
            <td>
              <StatusBadge status={r.status} />
            </td>
            <td>{r.domain}</td>
            <td className="muted">{r.pdf_filename ?? "—"}</td>
            <td className="muted">
              {new Date(r.created_at).toLocaleString()}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
