"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createRun } from "@/lib/api";
import { useToast } from "@/components/Toasts";

export default function UploadPage() {
  const router = useRouter();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [regulationRef, setRegulationRef] = useState("RBI-MD-KYC-2016");
  const [domain, setDomain] = useState("banking");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Select a PDF to upload.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("pdf", file);
      form.append("regulation_ref", regulationRef);
      form.append("domain", domain);
      const { run_id } = await createRun(form);
      toast.push("success", `Run started: ${run_id.slice(0, 8)}…`);
      router.push(`/runs/${run_id}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      toast.push("error", `Upload failed: ${msg}`);
      setSubmitting(false);
    }
  }

  return (
    <>
      <h1>Start a compliance run</h1>
      <p>
        Upload a regulatory PDF. The pipeline will extract obligations, retrieve
        matching policies, classify gaps, score risk, and pause for your
        approval before generating the final report.
      </p>

      <form className="card" onSubmit={onSubmit}>
        <div style={{ marginBottom: 16 }}>
          <label>Regulation PDF</label>
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        <div className="row">
          <div>
            <label>Regulation reference</label>
            <input
              type="text"
              value={regulationRef}
              onChange={(e) => setRegulationRef(e.target.value)}
            />
          </div>
          <div>
            <label>Domain</label>
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            >
              <option value="banking">banking</option>
              <option value="insurance">insurance</option>
              <option value="capital_markets">capital_markets</option>
            </select>
          </div>
        </div>

        {error && <div className="error">{error}</div>}

        <div className="actions">
          <button type="submit" disabled={submitting}>
            {submitting ? "Starting…" : "Start run"}
          </button>
        </div>
      </form>
    </>
  );
}
