import type {
  ActiveRules,
  Simulation,
  AgentStatus,
  Authority,
  CaseClaims,
  CaseDetail,
  CaseReport,
  CaseStatus,
  CaseSummary,
  Outcome,
  ReportDraft,
  TaskStatus,
  AttributeVersion,
  ClusterResult,
  EntityDetail,
  GraphData,
  Job,
  AnalyticsRule,
  RuleDocument,
  RulePreview,
  Network,
  Me,
  Appearance,
  Overview,
  MergeExplanation,
  ReviewPair,
  RuleSet,
  SearchHit,
} from "./types";

export type AttributeMode = "shared" | "all" | "none";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// In OIDC mode the shell stores the access token here after sign-in (Phase 4 wires the IdP).
let accessToken: string | null = null;
export const setAccessToken = (token: string | null) => {
  accessToken = token;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && typeof init.body === "string") headers.set("Content-Type", "application/json");
  const res = await fetch(`/api/v1${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const qs = (params: Record<string, string | number | undefined>) =>
  new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)]),
  ).toString();

export const api = {
  me: () => request<Me>("/me"),
  overview: () => request<Overview>("/graph/overview"),
  entityNetwork: (id: string) =>
    request<Network>(`/graph/entities/${encodeURIComponent(id)}/network`),
  analyticsRules: () => request<AnalyticsRule[]>("/analytics/rules"),
  createAnalyticsRule: (doc: RuleDocument) =>
    request<AnalyticsRule>("/analytics/rules", { method: "POST", body: JSON.stringify(doc) }),
  previewAnalyticsRule: (doc: RuleDocument) =>
    request<RulePreview>("/analytics/rules/preview", { method: "POST", body: JSON.stringify(doc) }),
  publishAnalyticsRule: (id: string) =>
    request<AnalyticsRule>(`/analytics/rules/${id}/publish`, { method: "POST" }),
  retireAnalyticsRule: (id: string) =>
    request<AnalyticsRule>(`/analytics/rules/${id}/retire`, { method: "POST" }),
  deleteAnalyticsRule: (id: string) =>
    request<void>(`/analytics/rules/${id}`, { method: "DELETE" }),
  search: (q: string, type?: string) => request<SearchHit[]>(`/search?${qs({ q, type })}`),
  cases: () => request<CaseSummary[]>("/cases"),
  caseClaims: (key: string) =>
    request<CaseClaims>(`/cases/${encodeURIComponent(key)}/claims`),
  caseDetail: (key: string) => request<CaseDetail>(`/cases/${encodeURIComponent(key)}`),
  updateCase: (key: string, patch: { status?: CaseStatus; assignee?: string | null }) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}`, { method: "PATCH", body: JSON.stringify(patch) }),
  addCaseNote: (key: string, body: { title: string; body: string; task_id?: string | null }) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}/notes`, { method: "POST", body: JSON.stringify(body) }),
  updateCaseNote: (key: string, id: string, patch: { title?: string; body?: string; task_id?: string | null }) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}/notes/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteCaseNote: (key: string, id: string) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}/notes/${id}`, { method: "DELETE" }),
  tagCaseDocument: (key: string, id: string, task_id: string | null) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}/documents/${id}`, { method: "PATCH", body: JSON.stringify({ task_id }) }),
  agentStatus: () => request<AgentStatus>("/cases/agent/status"),
  draftReport: (key: string) =>
    request<ReportDraft>(`/cases/${encodeURIComponent(key)}/report/draft`, { method: "POST" }),
  addCaseTask: (key: string, body: { title: string; assignee?: string | null; due_date?: string | null }) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}/tasks`, { method: "POST", body: JSON.stringify(body) }),
  updateCaseTask: (
    key: string,
    id: string,
    patch: { title?: string; assignee?: string | null; due_date?: string | null; status?: TaskStatus; done?: boolean },
  ) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}/tasks/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteCaseTask: (key: string, id: string) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}/tasks/${id}`, { method: "DELETE" }),
  uploadCaseDocument: (key: string, file: File, note: string, taskId?: string | null) => {
    const form = new FormData();
    form.append("file", file);
    if (note) form.append("note", note);
    if (taskId) form.append("task_id", taskId);
    return request<CaseDetail>(`/cases/${encodeURIComponent(key)}/documents`, { method: "POST", body: form });
  },
  caseDocumentUrl: (key: string, id: string) => `/api/v1/cases/${encodeURIComponent(key)}/documents/${id}`,
  deleteCaseDocument: (key: string, id: string) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}/documents/${id}`, { method: "DELETE" }),
  saveCaseReport: (key: string, report: CaseReport) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}/report`, { method: "PUT", body: JSON.stringify(report) }),
  closeCase: (key: string, body: { outcome: Outcome; summary: string; recommendation: string; amount_recovered: number | null; authority: Authority }) =>
    request<CaseDetail>(`/cases/${encodeURIComponent(key)}/close`, { method: "POST", body: JSON.stringify(body) }),
  neighborhood: (id: string, hops: number, attributes: AttributeMode = "shared", limit = 500) =>
    request<GraphData>(`/graph/neighborhood?${qs({ id, hops, limit, attributes })}`),
  path: (from: string, to: string) =>
    request<GraphData>(`/graph/path?${qs({ from, to })}`),
  entityRecords: (id: string) =>
    request<GraphData>(`/graph/entities/${encodeURIComponent(id)}/records`),
  entity: (id: string) => request<EntityDetail>(`/entities/${encodeURIComponent(id)}`),
  attributes: (id: string) =>
    request<AttributeVersion[]>(`/entities/${encodeURIComponent(id)}/attributes`),
  appearances: (id: string) =>
    request<Appearance[]>(`/entities/${encodeURIComponent(id)}/appearances`),
  explain: (id: string) =>
    request<MergeExplanation[]>(`/entities/${encodeURIComponent(id)}/explain`),

  activeRules: (entityType: string) =>
    request<ActiveRules>(`/resolution/active?${qs({ entity_type: entityType })}`),
  simulate: (entityType: string, document: unknown) =>
    request<Simulation>("/resolution/simulate", {
      method: "POST",
      body: JSON.stringify({ entity_type: entityType, document }),
    }),
  ruleSets: () => request<RuleSet[]>("/resolution/rule-sets"),
  createRuleSet: (body: { name: string; entity_type: string; document: unknown }) =>
    request<RuleSet>("/resolution/rule-sets", { method: "POST", body: JSON.stringify(body) }),
  publishRuleSet: (id: string) =>
    request<{ job_id: string }>(`/resolution/rule-sets/${id}/publish`, { method: "POST" }),
  rollbackRuleSet: (id: string) =>
    request<{ job_id: string }>(`/resolution/rule-sets/${id}/rollback`, { method: "POST" }),
  runResolution: () => request<{ job_id: string }>("/resolution/runs", { method: "POST" }),
  reviewQueue: () => request<ReviewPair[]>("/resolution/review-queue"),
  decide: (body: { kind: string; record_ids: string[]; reason?: string; review_pair_id?: string }) =>
    request<{ override_id: string }>("/resolution/decisions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  clusters: (minScore = 0) => request<ClusterResult[]>(`/analytics/clusters?${qs({ min_score: minScore })}`),
  jobs: (kind?: string) => request<Job[]>(`/jobs?${qs({ kind })}`),
};
