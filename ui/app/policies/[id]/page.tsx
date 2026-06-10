"use client";

import Link from "next/link";
import { use } from "react";
import useSWR from "swr";
import { fetcher, type Policy } from "@/lib/api";

export default function PolicyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const decoded = decodeURIComponent(id);
  const { data, error, isLoading } = useSWR<Policy>(
    `/policies/${encodeURIComponent(decoded)}`,
    fetcher,
  );

  return (
    <>
      <div className="page-header">
        <h1>
          Policy{" "}
          <span style={{ fontFamily: "monospace", fontSize: 14 }}>{decoded}</span>
        </h1>
        <Link href="/policies">
          <button className="secondary">← Back</button>
        </Link>
      </div>

      {error && (
        <div className="error">
          {String(error.message)}.{" "}
          <Link href="/settings">Check Settings</Link>.
        </div>
      )}

      {isLoading && <div className="muted">Loading…</div>}

      {data && (
        <>
          <div className="card">
            <div className="summary-grid">
              <div className="summary-tile">
                <span className="lbl">Domain</span>
                <span className="num" style={{ fontSize: 16 }}>
                  {data.domain}
                </span>
              </div>
              <div className="summary-tile">
                <span className="lbl">Section</span>
                <span className="num" style={{ fontSize: 16 }}>
                  {data.section ?? "—"}
                </span>
              </div>
              <div className="summary-tile">
                <span className="lbl">Owner</span>
                <span className="num" style={{ fontSize: 16 }}>
                  {data.owner ?? "—"}
                </span>
              </div>
              <div className="summary-tile">
                <span className="lbl">Created</span>
                <span className="num" style={{ fontSize: 13 }}>
                  {data.created_at
                    ? new Date(data.created_at).toLocaleDateString()
                    : "—"}
                </span>
              </div>
            </div>
          </div>

          <div className="card">
            <h2 style={{ marginTop: 0 }}>{data.title}</h2>
            {(() => {
              const tags = (data.tags ?? "")
                .split(",")
                .map((t) => t.trim())
                .filter(Boolean);
              if (tags.length === 0) return null;
              return (
                <div
                  style={{
                    display: "flex",
                    gap: 6,
                    flexWrap: "wrap",
                    marginBottom: 12,
                  }}
                >
                  {tags.map((t) => (
                    <span key={t} className="status-badge status-pending">
                      {t}
                    </span>
                  ))}
                </div>
              );
            })()}
            <pre
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontFamily: "inherit",
                fontSize: 14,
                lineHeight: 1.6,
                margin: 0,
              }}
            >
              {data.text}
            </pre>
          </div>
        </>
      )}
    </>
  );
}
