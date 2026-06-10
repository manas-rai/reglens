"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { SkeletonRows } from "@/components/Skeleton";
import { fetcher, type PolicyListResponse } from "@/lib/api";

const DOMAINS = ["banking", "healthcare", "energy"];
const PAGE_SIZE = 20;

export default function PoliciesPage() {
  const [domain, setDomain] = useState("");
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);

  const params = new URLSearchParams();
  if (domain) params.set("domain", domain);
  if (q) params.set("q", q);
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(offset));

  const { data, error, isLoading } = useSWR<PolicyListResponse>(
    `/policies?${params.toString()}`,
    fetcher,
  );

  const items = data?.items ?? [];
  const hasNext = items.length === PAGE_SIZE;

  function applySearch(e: React.FormEvent) {
    e.preventDefault();
    setQ(qInput.trim());
    setOffset(0);
  }

  return (
    <>
      <div className="page-header">
        <h1>Policies</h1>
      </div>

      <div className="filters">
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
        <form onSubmit={applySearch} style={{ flex: 1, display: "flex", gap: 8 }}>
          <div style={{ flex: 1 }}>
            <label>Search</label>
            <input
              type="text"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="id, title, or text…"
            />
          </div>
          <button type="submit" className="secondary" style={{ alignSelf: "flex-end" }}>
            Search
          </button>
        </form>
      </div>

      {error && (
        <div className="error">
          Cannot reach API: {String(error.message)}. Check{" "}
          <Link href="/settings">Settings</Link>.
        </div>
      )}

      <div className="card">
        {isLoading ? (
          <SkeletonRows rows={5} cols={5} />
        ) : items.length === 0 ? (
          <div className="empty">No policies match these filters.</div>
        ) : (
          <table className="risk-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Domain</th>
                <th>Section</th>
                <th>Title</th>
                <th>Owner</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link
                      href={`/policies/${encodeURIComponent(p.id)}`}
                      className="run-row-link"
                    >
                      {p.id}
                    </Link>
                  </td>
                  <td>{p.domain}</td>
                  <td className="muted">{p.section ?? "—"}</td>
                  <td>{p.title}</td>
                  <td className="muted">{p.owner ?? "—"}</td>
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
