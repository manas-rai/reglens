"use client";

import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import {
  approveRun,
  getDraft,
  type ComplianceReport,
  type Edit,
} from "@/lib/api";

const STATUSES = ["compliant", "partial_gap", "gap", "not_applicable"];

export default function ReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const [draft, setDraft] = useState<ComplianceReport | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getDraft(id)
      .then(setDraft)
      .catch((e) => setError(String(e)));
  }, [id]);

  function setOverride(obligationId: string, status: string, current: string) {
    setOverrides((prev) => {
      const next = { ...prev };
      if (status === current) delete next[obligationId];
      else next[obligationId] = status;
      return next;
    });
  }

  async function submit(approved: boolean) {
    setSubmitting(true);
    setError(null);
    try {
      const edits: Edit[] = approved
        ? Object.entries(overrides).map(([obligation_id, status]) => ({
            obligation_id,
            status,
          }))
        : [];
      await approveRun(id, approved, edits);
      router.push(approved ? `/runs/${id}/report` : `/runs/${id}`);
    } catch (e) {
      setError(String(e));
      setSubmitting(false);
    }
  }

  if (error && !draft) return <div className="error">{error}</div>;
  if (!draft) return <p>Loading draft report…</p>;

  return (
    <>
      <h1>Review draft report</h1>
      <p>
        {draft.regulation_ref} · {draft.domain} ·{" "}
        {draft.summary.total_obligations} obligations
      </p>

      <div className="card">
        <div className="summary-grid">
          <Tile n={draft.summary.compliant} l="Compliant" />
          <Tile n={draft.summary.partial_gap} l="Partial gap" />
          <Tile n={draft.summary.gap} l="Gap" />
          <Tile n={draft.summary.not_applicable} l="N/A" />
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
            {draft.risk_scores.map((rs) => {
              const obligationId = rs.gap_result.obligation.id;
              const current = rs.gap_result.status;
              const override = overrides[obligationId];
              return (
                <tr key={obligationId}>
                  <td>
                    <strong>{obligationId}</strong>
                    <div className="muted">
                      {rs.gap_result.obligation.clause}
                    </div>
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

      {error && <div className="error">{error}</div>}

      <div className="actions">
        <button onClick={() => submit(true)} disabled={submitting}>
          Approve {Object.keys(overrides).length > 0
            ? `with ${Object.keys(overrides).length} edit(s)`
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

function Tile({ n, l }: { n: number; l: string }) {
  return (
    <div className="summary-tile">
      <span className="num">{n}</span>
      <span className="lbl">{l}</span>
    </div>
  );
}
