"use client";

import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { eventsUrl, getRun } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

interface PipelineEvent {
  node: string;
  status: string;
  detail?: string;
  ts: string;
}

const TERMINAL = new Set(["completed", "rejected", "error", "awaiting_approval"]);

export default function RunProgressPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [status, setStatus] = useState<string>("pending");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const es = new EventSource(eventsUrl(id));

    es.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as Omit<PipelineEvent, "ts">;
        const evt: PipelineEvent = {
          ...data,
          ts: new Date().toLocaleTimeString(),
        };
        setEvents((prev) => [...prev, evt]);
        if (data.status) setStatus(data.status);
        if (TERMINAL.has(data.status)) {
          es.close();
          if (data.status === "awaiting_approval") {
            router.push(`/runs/${id}/review`);
          } else if (data.status === "completed") {
            router.push(`/runs/${id}/report`);
          }
        }
      } catch (e) {
        console.error("event parse", e);
      }
    };

    es.onerror = () => {
      es.close();
      getRun(id)
        .then((r) => {
          setStatus(r.status);
          if (r.status === "awaiting_approval") {
            router.push(`/runs/${id}/review`);
          } else if (r.status === "completed") {
            router.push(`/runs/${id}/report`);
          } else if (r.error_message) {
            setError(r.error_message);
          }
        })
        .catch((err) => setError(String(err)));
    };

    return () => es.close();
  }, [id, router]);

  return (
    <>
      <h1>
        Run{" "}
        <span style={{ fontFamily: "monospace", fontSize: 14 }}>{id}</span>
      </h1>
      <p>
        Status: <StatusBadge status={status} />
      </p>

      {error && <div className="error">{error}</div>}

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Pipeline events</h2>
        <div className="event-log">
          {events.length === 0 ? (
            <div className="muted">Waiting for first event…</div>
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
    </>
  );
}
