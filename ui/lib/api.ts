export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "dev-key";

function authHeaders(): HeadersInit {
  return { "x-api-key": API_KEY };
}

export interface RunStatus {
  run_id: string;
  status: string;
  domain: string;
  pdf_filename: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface RiskScore {
  gap_result: {
    obligation: { id: string; clause: string; text: string };
    status: string;
    gap_description?: string | null;
    recommendation?: string | null;
    reasoning: string;
  };
  risk_level: string;
  score: number;
  justification: string;
}

export interface RunSummary {
  total_obligations: number;
  compliant: number;
  partial_gap: number;
  gap: number;
  not_applicable: number;
  by_risk_level: Record<string, number>;
}

export interface ComplianceReport {
  run_id: string;
  regulation_ref: string;
  domain: string;
  generated_at: string;
  summary: RunSummary;
  risk_scores: RiskScore[];
  markdown: string;
}

export interface Edit {
  obligation_id: string;
  status?: string;
}

export async function createRun(form: FormData): Promise<{ run_id: string }> {
  const res = await fetch(`${API_BASE_URL}/runs`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error(`createRun failed: ${res.status}`);
  return res.json();
}

export async function getRun(runId: string): Promise<RunStatus> {
  const res = await fetch(`${API_BASE_URL}/runs/${runId}`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`getRun failed: ${res.status}`);
  return res.json();
}

export async function getDraft(runId: string): Promise<ComplianceReport> {
  const res = await fetch(`${API_BASE_URL}/runs/${runId}/draft`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`getDraft failed: ${res.status}`);
  const body = (await res.json()) as { draft_report: ComplianceReport };
  return body.draft_report;
}

export async function getReport(runId: string): Promise<ComplianceReport> {
  const res = await fetch(`${API_BASE_URL}/runs/${runId}/report`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`getReport failed: ${res.status}`);
  return res.json();
}

export async function approveRun(
  runId: string,
  approved: boolean,
  edits: Edit[] = [],
): Promise<{ run_id: string; status: string }> {
  const res = await fetch(`${API_BASE_URL}/runs/${runId}/approve`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ approved, edits }),
  });
  if (!res.ok) throw new Error(`approveRun failed: ${res.status}`);
  return res.json();
}

export function eventsUrl(runId: string): string {
  const url = new URL(`${API_BASE_URL}/runs/${runId}/events`);
  url.searchParams.set("x-api-key", API_KEY);
  return url.toString();
}
