// API client: every call reads base URL + key from the in-memory store
// hydrated from localStorage on the client. SSR has no window, so reads
// fall back to env vars (kept for local dev parity with the backend
// docker-compose URL).

const LS_BASE_URL = "reglens.apiBaseUrl";
const LS_API_KEY = "reglens.apiKey";

const ENV_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const ENV_API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

export function getApiBaseUrl(): string {
  if (typeof window === "undefined") return ENV_BASE_URL;
  return window.localStorage.getItem(LS_BASE_URL) || ENV_BASE_URL;
}

export function getApiKey(): string {
  if (typeof window === "undefined") return ENV_API_KEY;
  return window.localStorage.getItem(LS_API_KEY) || ENV_API_KEY;
}

export function setApiConfig(baseUrl: string, apiKey: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LS_BASE_URL, baseUrl);
  window.localStorage.setItem(LS_API_KEY, apiKey);
}

export function hasApiKey(): boolean {
  return getApiKey().length > 0;
}

function authHeaders(): HeadersInit {
  return { "x-api-key": getApiKey() };
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

export interface RunListResponse {
  items: RunStatus[];
  limit: number;
  offset: number;
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

export interface Stats {
  total_runs: number;
  by_status: Record<string, number>;
  total_cost_usd: number;
}

export interface AuditEntry {
  id: number;
  node: string;
  actor: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface CostEntry {
  id: number;
  agent: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  created_at: string;
}

export interface CostResponse {
  items: CostEntry[];
  total_cost_usd: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
}

export interface GapResult {
  obligation: { id: string; clause: string; text: string };
  status: string;
  gap_description?: string | null;
  recommendation?: string | null;
  reasoning: string;
}

export interface Policy {
  id: string;
  domain: string;
  section: string | null;
  title: string;
  text: string;
  owner: string | null;
  tags: string[] | null;
  created_at: string | null;
}

export interface PolicyListResponse {
  items: Policy[];
  limit: number;
  offset: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text || path}`);
  }
  return res.json() as Promise<T>;
}

export const fetcher = <T>(path: string): Promise<T> => request<T>(path);

export async function createRun(form: FormData): Promise<{ run_id: string }> {
  const res = await fetch(`${getApiBaseUrl()}/runs`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error(`createRun failed: ${res.status}`);
  return res.json();
}

export const getRun = (runId: string) => request<RunStatus>(`/runs/${runId}`);

export const listRuns = (params: {
  status?: string;
  domain?: string;
  limit?: number;
  offset?: number;
}) => {
  const sp = new URLSearchParams();
  if (params.status) sp.set("status", params.status);
  if (params.domain) sp.set("domain", params.domain);
  sp.set("limit", String(params.limit ?? 20));
  sp.set("offset", String(params.offset ?? 0));
  return request<RunListResponse>(`/runs?${sp.toString()}`);
};

export const getStats = () => request<Stats>("/stats");

export const listPolicies = (params: {
  domain?: string;
  q?: string;
  limit?: number;
  offset?: number;
}) => {
  const sp = new URLSearchParams();
  if (params.domain) sp.set("domain", params.domain);
  if (params.q) sp.set("q", params.q);
  sp.set("limit", String(params.limit ?? 20));
  sp.set("offset", String(params.offset ?? 0));
  return request<PolicyListResponse>(`/policies?${sp.toString()}`);
};

export const getPolicy = (policyId: string) =>
  request<Policy>(`/policies/${encodeURIComponent(policyId)}`);

export const getDraft = (runId: string) =>
  request<{ draft_report: ComplianceReport }>(`/runs/${runId}/draft`).then(
    (b) => b.draft_report,
  );

export const getReport = (runId: string) =>
  request<ComplianceReport>(`/runs/${runId}/report`);

export const getAudit = (runId: string) =>
  request<{ items: AuditEntry[] }>(`/runs/${runId}/audit`);

export const getCosts = (runId: string) =>
  request<CostResponse>(`/runs/${runId}/costs`);

export const getGaps = (runId: string) =>
  request<{ items: GapResult[] }>(`/runs/${runId}/gaps`);

export async function approveRun(
  runId: string,
  approved: boolean,
  edits: Edit[] = [],
): Promise<{ run_id: string; status: string }> {
  return request(`/runs/${runId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, edits }),
  });
}

export function eventsUrl(runId: string): string {
  const url = new URL(`${getApiBaseUrl()}/runs/${runId}/events`);
  url.searchParams.set("x-api-key", getApiKey());
  return url.toString();
}
