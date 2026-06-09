"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { StatusBadge } from "@/components/StatusBadge";
import { fetcher, type RunListResponse } from "@/lib/api";

const STATUSES = [
  "pending",
  "running",
  "awaiting_approval",
  "completed",
  "rejected",
  "error",
];

const DOMAINS = ["banking", "healthcare", "energy"];

const PAGE_SIZE = 20;

export default function RunsListPage() {
  const [status, setStatus] = useState("");
  const [domain, setDomain] = useState("");
  const [offset, setOffset] = useState(0);

  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (domain) params.set("domain", domain);
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(offset));

  const { data, error, isLoading } = useSWR<RunListResponse>(
    `/runs?${params.toString()}`,
    fetcher,
    { refreshInterval: 5000 },
  );

  const items = data?.items ?? [];
  const hasNext = items.length === PAGE_SIZE;

  return (
    <>
      <div className="page-header">
        <h1>Runs</h1>
        <Link href="/runs/new">
          <button>New run</button>
        </Link>
      </div>

      <div className="filters">
        <div>
          <label>Status</label>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label>Domain</label>
          <select
            value={domain}
            onChange={(e) => {
              setDomain(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All</option>
            {DOMAINS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="error">
          Cannot reach API: {String(error.message)}. Check{" "}
          <Link href="/settings">Settings</Link>.
        </div>
      )}

      <div className="card">
        {isLoading ? (
          <div className="muted">Loading…</div>
        ) : items.length === 0 ? (
          <div className="empty">
            No runs match these filters.{" "}
            <Link href="/runs/new">Start one →</Link>
          </div>
        ) : (
          <table className="risk-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th>Domain</th>
                <th>File</th>
                <th>Created</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.run_id}>
                  <td>
                    <Link
                      href={`/runs/${r.run_id}`}
                      className="run-row-link"
                    >
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
                  <td className="muted">
                    {new Date(r.updated_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="pager">
          <button
            className="secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            ← Prev
          </button>
          <span className="muted">
            {items.length === 0
              ? "—"
              : `${offset + 1}–${offset + items.length}`}
          </span>
          <button
            className="secondary"
            disabled={!hasNext}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next →
          </button>
        </div>
      </div>
    </>
  );
}
