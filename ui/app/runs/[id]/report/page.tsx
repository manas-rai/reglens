"use client";

import { use, useEffect, useState } from "react";
import { getReport, type ComplianceReport } from "@/lib/api";

const LEVEL_ORDER = ["critical", "high", "medium", "low", "none"];

export default function ReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [report, setReport] = useState<ComplianceReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getReport(id)
      .then(setReport)
      .catch((e) => setError(String(e)));
  }, [id]);

  if (error) return <div className="error">{error}</div>;
  if (!report) return <p>Loading report…</p>;

  const sorted = [...report.risk_scores].sort(
    (a, b) =>
      LEVEL_ORDER.indexOf(a.risk_level) - LEVEL_ORDER.indexOf(b.risk_level),
  );

  return (
    <>
      <h1>Compliance report</h1>
      <p>
        {report.regulation_ref} · {report.domain} · generated{" "}
        {new Date(report.generated_at).toLocaleString()}
      </p>

      <div className="card">
        <div className="summary-grid">
          <Tile n={report.summary.compliant} l="Compliant" />
          <Tile n={report.summary.partial_gap} l="Partial gap" />
          <Tile n={report.summary.gap} l="Gap" />
          <Tile n={report.summary.not_applicable} l="N/A" />
        </div>
      </div>

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
        <h2 style={{ marginTop: 0 }}>Findings</h2>
        {sorted.map((rs) => (
          <div
            key={rs.gap_result.obligation.id}
            style={{
              padding: "12px 0",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>{rs.gap_result.obligation.id}</strong>
              <span className={`risk-${rs.risk_level}`}>
                {rs.risk_level.toUpperCase()} · {rs.score.toFixed(1)}
              </span>
            </div>
            <div className="muted" style={{ margin: "4px 0" }}>
              {rs.gap_result.obligation.clause} — status:{" "}
              {rs.gap_result.status.replace(/_/g, " ")}
            </div>
            <div style={{ fontSize: 13 }}>{rs.gap_result.obligation.text}</div>
            {rs.gap_result.gap_description && (
              <div style={{ marginTop: 8, fontSize: 13 }}>
                <strong>Gap:</strong> {rs.gap_result.gap_description}
              </div>
            )}
            {rs.gap_result.recommendation && (
              <div style={{ marginTop: 4, fontSize: 13 }}>
                <strong>Recommendation:</strong> {rs.gap_result.recommendation}
              </div>
            )}
            <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
              {rs.justification}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function Tile({ n, l }: { n: number; l: string }) {
  return (
    <div className="summary-tile">
      <span className="num">{n}</span>
      <span className="lbl">{l}</span>
    </div>
  );
}
