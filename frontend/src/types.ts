/** Mirrors the backend's versioned agent output contracts
 * (`newsroom_fleet.domain.contracts`) and the `article_view` payload. */

export type Role = "reporter" | "editor" | "service";

export type Desk =
  | "claim_extractor"
  | "source_verifier"
  | "data_checker"
  | "standards_reviewer"
  | "verdict_aggregator"
  | "corrections_watcher";

export type ClaimType = "numeric" | "quotation" | "attribution" | "legal_status" | "general";
export type RiskTier = "low" | "medium" | "high";
export type VerdictResult = "verified" | "contradicted" | "unsupported" | "abstain" | "error";
export type SecurityDisposition = "clean" | "quarantined" | "blocked";
export type EditorDisposition = "approve" | "send_back";
export type Materiality = "material" | "immaterial";
export type WatcherStatus = "pending_editor_review" | "disposed";

export type PublicationState =
  | "draft"
  | "reviewing"
  | "human_review"
  | "editor_ready"
  | "editor_approved"
  | "published"
  | "recheck_pending"
  | "correction_candidate";

export interface Source {
  source_id: string;
  kind: string;
  name: string;
  content: string;
  metadata: Record<string, unknown>;
}

export interface Article {
  article_id: string;
  title: string;
  body: string;
  author: string;
  submitted_at: string;
  sources: Source[];
}

export interface Claim {
  claim_id: string;
  article_id: string;
  text: string;
  span: [number, number];
  type: ClaimType;
  entities: string[];
  source_refs: string[];
  risk_tier: RiskTier;
  required_desks: Desk[];
  extractor_version: string;
}

export interface EvidenceRef {
  source_identity: string;
  locator: string;
  excerpt: string;
  retrieved_at: string;
}

export interface Verdict {
  schema_version: string;
  verdict_id: string;
  article_id: string;
  claim_id: string;
  desk: Desk;
  agent_version: string;
  result: VerdictResult;
  confidence: number;
  needs_human: boolean;
  reason: string;
  flags: string[];
  evidence: EvidenceRef[];
  error_detail: string | null;
  created_at: string;
}

export interface SecurityResult {
  security_id: string;
  article_id: string;
  source_id: string | null;
  disposition: SecurityDisposition;
  detector: string;
  detector_detail: string;
  policy_version: string;
  source_hash: string;
  sanitized_ref: string | null;
  created_at: string;
}

export interface EditorDecision {
  decision_id: string;
  article_id: string;
  actor: string;
  role: Role;
  disposition: EditorDisposition;
  rationale: string;
  revised_text: string | null;
  resolved_verdict_ids: string[];
  created_at: string;
}

export interface ClaimSnapshot {
  article_id: string;
  claim_id: string;
  claim_text: string;
  adapter_key: string;
  published_value: string;
  locator: string;
  recorded_at: string;
}

export interface WatcherResult {
  watcher_id: string;
  article_id: string;
  claim_id: string;
  prior_value: string;
  prior_locator: string;
  current_value: string;
  current_locator: string;
  materiality: Materiality;
  candidate_language: string;
  status: WatcherStatus;
  created_at: string;
}

export interface ClaimAssessment {
  claim_id: string;
  ok: boolean;
  missing_desks: Desk[];
  blocking_verdict_ids: string[];
  blocking_reasons: string[];
  conflict: boolean;
}

export interface GateReport {
  article_id: string;
  state: PublicationState;
  assessments: ClaimAssessment[];
  blocked_claim_ids: string[];
  blocking_verdict_ids: string[];
}

export interface ArticleView {
  article: Article;
  state: PublicationState;
  published_text: string | null;
  claims: Claim[];
  verdicts: Verdict[];
  security_results: SecurityResult[];
  decisions: EditorDecision[];
  snapshots: ClaimSnapshot[];
  watcher_results: WatcherResult[];
  gate: GateReport;
}

export interface AuditEvent {
  event_id: string;
  event_type: string;
  article_id: string;
  actor: string;
  claim_id: string | null;
  latency_ms: number | null;
  payload: Record<string, unknown>;
  ts: string;
}

export interface DeskRegistration {
  desk: Desk;
  agent_version: string;
  /** What the Masthead registers, vs. `agent_version` which is what is running. */
  registered_version?: string;
  schema_version: string;
  permissions: string[];
  responsibility: string;
}

/** Which implementation sits behind each interface in the running process.
 * `resolved` is what was actually constructed — a cloud component that fell
 * back to its local implementation reports the fallback, not the request. */
export interface Runtime {
  requested: {
    mode: string;
    repository: string;
    screener: string;
    queue: string;
    memory: string;
    tracing: string;
    pii_classifier: string;
    gcp_project: string | null;
    gcp_location: string;
    models: { reasoning: string | null; pii: string | null };
    authoritative_dataset: string;
    uses_cloud: boolean;
  };
  resolved: Record<string, string>;
}

export interface Identity {
  actor: string;
  role: Role;
}
