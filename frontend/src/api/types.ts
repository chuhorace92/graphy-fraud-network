// Mirrors backend/graphy/schemas. Regenerate from /api/openapi.json once the contract settles.

export type NodeKind = "Entity" | "Group" | "SourceRecord" | "AttributeValue" | "Cluster";

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  parent: string | null;
  entity_type: string | null;
  score: number | null;
  status: string | null;
  data: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string | null;
  data: Record<string, unknown>;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
}

export interface EntityDetail {
  entity_id: string;
  entity_type: string;
  canonical_name: string | null;
  rule_set_version: string | null;
  record_count: number;
  groups: { group_id: string; group_type: string; role: string | null }[];
}

export interface AttributeVersion {
  attr_type: string;
  value_id: string;
  display: string;
  source_system: string | null;
  record_id: string;
  first_seen: string | null;
  last_seen: string | null;
  is_current: boolean;
  is_hub: boolean;
  shared_with: number;
}

export interface MergeExplanation {
  record_id: string;
  source_system: string | null;
  method: string | null;
  score: number | null;
  rules_fired: string[];
  rule_set_version: string | null;
}

export interface Overview {
  claims: number;
  policies: number;
  people: number;
  companies: number;
  groups: number;
  largest_group: number;
  people_records: number;
  merged_people: number;
  merged_records: number;
}

export interface Appearance {
  record_id: string;
  source_system: string | null;
  name: string | null;
  links: { claim_id: string; claim: string; role: string }[];
  attributes: { attr_type: string; display: string }[];
}

export interface SearchHit {
  entity_id: string;
  label: string;
  entity_type: string;
  matched_on: string;
  score: number;
}

export interface RuleSet {
  id: string;
  name: string;
  entity_type: string;
  version: number;
  state: "draft" | "simulated" | "published" | "retired";
  document: Record<string, unknown>;
  created_by: string;
  created_at: string;
  published_at: string | null;
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  params: Record<string, unknown>;
  counts: Record<string, unknown>;
  error: string | null;
  created_by: string;
  created_at: string;
  finished_at: string | null;
}

export interface ClusterResult {
  id: string;
  run_id: string;
  cluster_id: string;
  score: number;
  reasons: Record<string, unknown>;
  metrics: Record<string, unknown>;
  change: string;
}

export interface ReviewContribution {
  attr: string;
  outcome: "match" | "similar" | "conflict" | "ignored";
  similarity: number;
  points: number;
  left: string;
  right: string;
  text: string;
}

export interface ReviewPair {
  id: string;
  record_a: string;
  record_b: string;
  score: number;
  status: string;
  contributions: {
    entity_type: string;
    label_a: string;
    label_b: string;
    reason: string;
    attrs: ReviewContribution[];
  };
}

export type ErType = "Person" | "Organization" | "Vehicle" | "LegalRep" | "MedicalProvider" | "BodyShop";
export type Strength = "off" | "low" | "medium" | "strong";

export interface AttributeScoring {
  strength: Strength;
  compare: "exact" | "fuzzy" | "name_parts" | "year";
  min_similarity: number;
  surname_exact: boolean;
  nicknames: boolean;
  on_conflict: "ignore" | "penalize" | "block";
  conflict_penalty: number;
  merge_alone: boolean;
  ignore_shared_over: number | null;
  ignore_legal_suffixes: boolean;
}

export interface Scoring {
  weights: { strong: number; medium: number; low: number };
  attributes: Record<string, AttributeScoring>;
  auto_merge: number;
  review: number;
  merge_by_score: boolean;
  require_identity_match: boolean;
  identity: string[];
}

export interface RuleDoc {
  scoring: Scoring;
  constraints: { max_cluster_size: number; max_block_size: number };
}

export interface ActiveRules {
  entity_type: ErType;
  name: string;
  version: string | null;
  document: RuleDoc;
}

export interface Simulation {
  records: number;
  entities: number;
  merged_records: number;
  merge_pairs: number;
  review_pairs: number;
  blocked_by_conflict: number;
  no_identity_match: number;
  current_entities: number;
  changed_groups: number;
  merges: { labels: string[]; records: number }[];
  reviews: { label_a: string; label_b: string; score: number; reason: string }[];
}

export interface RuleCondition {
  metric: string;
  op: ">=" | ">" | "<=" | "<" | "==";
  value: number;
  attr_type?: string | null;
  types?: string[] | null;
  min_claims?: number | null;
  window_days?: number | null;
}

export interface RuleDocument {
  rule_id: string;
  scope: "cluster" | "entity";
  conditions: RuleCondition[];
  severity: "low" | "medium" | "high";
  description: string | null;
  points?: number | null;
  points_each?: number | null;
}

export interface AnalyticsRule {
  id: string;
  rule_id: string;
  version: number;
  state: "draft" | "published" | "retired" | string;
  document: RuleDocument;
  created_by: string;
  created_at: string;
}

export interface RulePreview {
  networks_checked: number;
  networks_hit: number;
  examples: { network_id: string; focus_id: string; focus_label: string; size: number; detail: string }[];
}

export interface HitMatch {
  kind: "value" | "claims" | "group" | "person" | "alias";
  entities: string[];
  claims: string[];
  attr_type: string | null;
  value_id: string | null;
  value: string | null;
  note: string;
}

export interface Hit {
  rule_id: string;
  title: string;
  severity: "low" | "medium" | "high";
  points: number;
  detail: string;
  entities: string[];
  condition: string;
  matches: HitMatch[];
}

export interface Network {
  network_id: string;
  size: number;
  links: number;
  types: Record<string, number>;
  aliases: number;
  focus_id: string;
  focus_label: string;
  via: string[];
  score: number;
  severity: "low" | "medium" | "high";
  flags: string[];
  hits: Hit[];
  members: string[];
}

export interface Lead {
  entity_id: string;
  label: string;
  entity_type: string;
  connections: number;
  via: string[];
}

export interface Me {
  subject: string;
  roles: string[];
}

/* ------------------------------------------------------------------ case management */

export type CaseStatus = "new" | "investigating" | "confirmed" | "insufficient" | "dismissed";
export type Outcome = "confirmed" | "insufficient" | "dismissed";
export type TaskStatus = "pending" | "received" | "not_received";

export interface CaseSummary {
  case_key: string;
  status: CaseStatus;
  assignee: string | null;
  updated_at: string | null;
  focus_id: string;
  focus_label: string;
  size: number;
  links: number;
  types: Record<string, number>;
  aliases: number;
  via: string[];
  claim_count: number;
  claimed_amount: number;
  score: number;
  severity: "low" | "medium" | "high";
  flags: string[];
  open_tasks: number;
}

export interface CaseMember {
  entity_id: string;
  label: string;
  entity_type: string;
  claims: number;
  roles: string[];
}

export interface ClaimParty {
  entity_id: string;
  label: string;
  entity_type: string;
  role: string;
}

export interface CaseClaim {
  entity_id: string;
  claim: string;
  loss_date: string | null;
  fnol_date: string | null;
  loss_types: string[];
  description: string | null;
  status: string | null;
  amount: number | null;
  siu_referred: boolean;
  siu_accepted: boolean;
  siu_outcome: string | null;
  parties: ClaimParty[];
}

export interface CaseClaims {
  total: number;
  items: CaseClaim[];
}

export interface CaseEvent {
  id: string;
  kind: "note" | "status" | "assignee" | "task" | "document" | "report";
  body: string;
  author: string;
  created_at: string;
}

export interface CaseTask {
  id: string;
  title: string;
  assignee: string | null;
  due_date: string | null;
  status: TaskStatus;
  done: boolean;
  done_at: string | null;
  created_by: string;
  created_at: string;
}

export interface CaseDocument {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  note: string | null;
  task_id: string | null;
  uploaded_by: string;
  created_at: string;
}

export interface CaseNote {
  id: string;
  title: string;
  body: string; // sanitized HTML
  preview: string;
  task_id: string | null;
  created_by: string;
  created_at: string;
  updated_by: string | null;
  updated_at: string | null;
}

export interface Authority {
  reported: boolean;
  name: string;
  reference: string;
  reported_on: string | null;
  notes: string;
}

export interface CaseReport {
  outcome: Outcome | null;
  summary: string;
  recommendation: string;
  amount_recovered: number | null;
  authority: Authority;
}

export interface CaseDetail {
  summary: CaseSummary;
  network: Network;
  members: CaseMember[];
  events: CaseEvent[];
  tasks: CaseTask[];
  documents: CaseDocument[];
  notes: CaseNote[];
  report: CaseReport | null;
  closed_at: string | null;
  closed_by: string | null;
}

export interface UnreadDocument {
  filename: string;
  reason: string;
}

export interface ReportDraft {
  outcome: Outcome | null;
  summary: string;
  recommendation: string;
  amount_recovered: number | null;
  caveats: string[];
  used_documents: string[];
  used_notes: number;
  unread: UnreadDocument[];
  model: string;
}

export interface AgentStatus {
  enabled: boolean;
  model: string;
}
