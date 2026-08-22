import type {
  BulkLlmExtractionResult,
  ConflictStatus,
  ConflictView,
  DashboardSummary,
  DocumentSummary,
  EntityDetail,
  EntitySummary,
  EventView,
  FactView,
  LlmExtractionResult,
  LlmStatus,
  SyncResult,
} from "../types/api";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(
      response.status,
      `${init?.method ?? "GET"} ${path} failed (${response.status}): ${body}`,
    );
  }

  return response.json() as Promise<T>;
}

export const api = {
  dashboard: () => request<DashboardSummary>("/api/dashboard"),

  syncVault: () => request<SyncResult>("/api/vault/sync", { method: "POST" }),

  documents: () => request<DocumentSummary[]>("/api/documents"),

  llmStatus: () => request<LlmStatus>("/api/llm/status"),

  extractLlmFacts: (documentId: number) =>
    request<LlmExtractionResult>(
      `/api/documents/${documentId}/extract-llm-facts`,
      { method: "POST" },
    ),

  extractLlmFactsBulk: (force = false) =>
    request<BulkLlmExtractionResult>(
      `/api/vault/extract-llm-facts?force=${force}`,
      { method: "POST" },
    ),

  entities: (entityType?: string) =>
    request<EntitySummary[]>(
      `/api/entities${entityType ? `?entity_type=${encodeURIComponent(entityType)}` : ""}`,
    ),

  entity: (id: number) => request<EntityDetail>(`/api/entities/${id}`),

  facts: (params?: { entityId?: number; predicate?: string }) => {
    const query = new URLSearchParams();
    if (params?.entityId) query.set("entity_id", String(params.entityId));
    if (params?.predicate) query.set("predicate", params.predicate);
    const suffix = query.toString() ? `?${query}` : "";
    return request<FactView[]>(`/api/facts${suffix}`);
  },

  events: () => request<EventView[]>("/api/events"),

  conflicts: (status?: ConflictStatus) =>
    request<ConflictView[]>(
      `/api/conflicts${status ? `?status=${status}` : ""}`,
    ),

  resolveConflict: (
    id: number,
    status: ConflictStatus,
    resolutionNote?: string,
  ) => {
    const query = new URLSearchParams({ status });
    if (resolutionNote) query.set("resolution_note", resolutionNote);
    return request<{ id: number; status: ConflictStatus }>(
      `/api/conflicts/${id}/resolve?${query}`,
      { method: "POST" },
    );
  },
};

export { ApiError };
