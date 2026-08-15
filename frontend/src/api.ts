import type {
  ArticleView,
  AuditEvent,
  Desk,
  DeskRegistration,
  EditorDecision,
  EditorDisposition,
  Identity,
  Runtime,
  WatcherResult,
} from "./types";

const BASE = "/api";

/** A server-side refusal carrying the Editor Gate's denial reasons.
 * The gate denies; it never mutates verdicts — so the reasons are the payload. */
export class ApiError extends Error {
  readonly status: number;
  readonly denials: string[];

  constructor(status: number, message: string, denials: string[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.denials = denials;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    let denials: string[] = [];
    try {
      const body = await response.json();
      const detail = body?.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (detail && typeof detail === "object") {
        message = detail.message ?? message;
        denials = Array.isArray(detail.denials) ? detail.denials : [];
      }
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new ApiError(response.status, message, denials);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => request<{ status: string; service: string }>("/health"),

  masthead: () => request<{ desks: DeskRegistration[]; implementation: string }>("/masthead"),

  runtime: () => request<Runtime>("/runtime"),

  listArticles: () =>
    request<{ articles: { article_id: string; state: string }[] }>("/articles"),

  getArticle: (articleId: string) => request<ArticleView>(`/articles/${articleId}`),

  getAudit: (articleId: string) => request<{ events: AuditEvent[] }>(`/articles/${articleId}/audit`),

  submitArticle: (payload: {
    title: string;
    body: string;
    author: string;
    sources?: { source_id: string; kind: string; name: string; content: string }[];
  }) => post<ArticleView>("/articles", payload),

  recordDecision: (
    articleId: string,
    identity: Identity,
    payload: {
      disposition: EditorDisposition;
      rationale: string;
      revised_text?: string | null;
      resolved_verdict_ids: string[];
    },
  ) => post<EditorDecision>(`/articles/${articleId}/decisions`, { ...identity, ...payload }),

  publish: (articleId: string, identity: Identity, decisionId?: string | null) =>
    post<{ allowed: boolean; state: string }>(`/articles/${articleId}/publish`, {
      ...identity,
      decision_id: decisionId ?? null,
    }),

  reReview: (articleId: string, identity: Identity) =>
    post<ArticleView>(`/articles/${articleId}/re-review`, identity),

  recheck: (articleId: string, identity: Identity) =>
    post<{ state: string; candidates: WatcherResult[] }>(
      `/articles/${articleId}/recheck`,
      identity,
    ),

  disposeCorrection: (
    articleId: string,
    watcherId: string,
    identity: Identity,
    payload: { accept: boolean; rationale: string; corrected_text?: string | null },
  ) =>
    post<ArticleView>(`/articles/${articleId}/corrections/${watcherId}/dispose`, {
      ...identity,
      ...payload,
    }),

  // ---- demo controls (fixture mode) ----
  loadGolden: () => post<ArticleView>("/demo/golden"),
  setFailDesk: (desk: Desk | null) => post<{ fail_desk: string | null }>("/demo/fail-desk", {
    fail_desk: desk,
  }),
  advanceData: () => post<{ authoritative_dataset: string }>("/demo/advance-data"),
};
