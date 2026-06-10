"use client";

import { useEffect, useState } from "react";
import { getApiBaseUrl, getApiKey, setApiConfig } from "@/lib/api";
import { useToast } from "@/components/Toasts";

export default function SettingsPage() {
  const toast = useToast();
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [probeStatus, setProbeStatus] = useState<
    "idle" | "ok" | "fail" | "checking"
  >("idle");
  const [probeMsg, setProbeMsg] = useState<string>("");

  useEffect(() => {
    setBaseUrl(getApiBaseUrl());
    setApiKey(getApiKey());
  }, []);

  function onSave(e: React.FormEvent) {
    e.preventDefault();
    setApiConfig(baseUrl.trim(), apiKey.trim());
    setSaved(true);
    toast.push("success", "API settings saved.");
    setTimeout(() => setSaved(false), 2000);
  }

  async function onTest() {
    setProbeStatus("checking");
    setProbeMsg("");
    try {
      const res = await fetch(`${baseUrl.trim()}/stats`, {
        headers: { "x-api-key": apiKey.trim() },
        cache: "no-store",
      });
      if (res.ok) {
        setProbeStatus("ok");
        setProbeMsg("Connection OK.");
      } else {
        setProbeStatus("fail");
        const text = await res.text().catch(() => "");
        setProbeMsg(`${res.status} ${res.statusText}: ${text}`);
      }
    } catch (err) {
      setProbeStatus("fail");
      setProbeMsg(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>API connection</h2>
        <p>
          These values are stored in your browser&apos;s localStorage. The API
          key is sent as the <code>x-api-key</code> header on every request.
        </p>
        <form onSubmit={onSave}>
          <div style={{ marginBottom: 16 }}>
            <label>API base URL</label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://localhost:8000"
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label>API key</label>
            <input
              type="text"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="your-api-key"
            />
          </div>
          <div className="actions">
            <button type="submit">Save</button>
            <button type="button" className="secondary" onClick={onTest}>
              Test connection
            </button>
            {saved && <span className="muted">Saved.</span>}
          </div>
        </form>

        {probeStatus === "ok" && (
          <div
            className="error"
            style={{
              color: "var(--green)",
              background: "rgba(69, 196, 116, 0.08)",
              borderColor: "rgba(69, 196, 116, 0.3)",
              marginTop: 16,
            }}
          >
            {probeMsg}
          </div>
        )}
        {probeStatus === "fail" && (
          <div className="error" style={{ marginTop: 16 }}>
            {probeMsg}
          </div>
        )}
        {probeStatus === "checking" && (
          <div className="muted" style={{ marginTop: 16 }}>
            Checking…
          </div>
        )}
      </div>
    </>
  );
}
