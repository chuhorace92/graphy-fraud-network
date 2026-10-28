import type { GraphEdge, GraphNode, MergeExplanation } from "../api/types";
import { VISUALS, type VisualKey } from "../graph/icons";

/** Plain-language wording for what the API reports in codes. */

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** Labels for attribute types that have no icon of their own. */
const LABELS: Record<string, string> = {
  siu_referred: "Referred to SIU",
  siu_accepted: "Accepted to SIU",
  siu_outcome: "SIU outcome",
  incorporation_date: "Date of incorporation",
  policy_inception_date: "Policy inception date",
  policy_expiry_date: "Policy expiry date",
  policy_type: "Policy type",
  policy_term: "Policy term",
  policy_status: "Policy status",
  plate_number: "Plate number",
  plate_state: "Plate state",
  vehicle_make: "Make",
  vehicle_model: "Model",
  vehicle_year: "Year",
};

/** A policy is named by its number. */
const NAME_LABEL: Record<string, string> = { Policy: "Policy number" };

export function attrLabel(type: string, entityType?: string | null): string {
  if (type === "name" && entityType && entityType in NAME_LABEL) return NAME_LABEL[entityType];
  return LABELS[type] ?? (type in VISUALS ? VISUALS[type as VisualKey].label : type.replace(/_/g, " "));
}

export const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);

const RULES: Record<string, string> = {
  "same-tax-id": "the same tax ID",
  "same-email": "the same email address",
  "same-phone": "the same phone number",
  "same-bank-acct": "the same bank account",
  manual: "a manual decision by an analyst",
};

export function ruleLabel(id: string): string {
  return RULES[id] ?? id.replace(/^same-/, "the same ").replace(/[-_]/g, " ");
}

/** "Two records were combined because they share the same tax ID and email address." */
export function mergeSummary(rows: MergeExplanation[], entityType: string): string {
  if (rows.length === 0) return "No source records found.";
  const rules = [...new Set(rows.flatMap((r) => r.rules_fired))].filter((r) => r !== "singleton");
  if (rows.length === 1 || rules.length === 0) {
    return "One source record. Nothing was combined.";
  }
  const sources = [...new Set(rows.map((r) => r.source_system).filter(Boolean))];
  const reasons = rules.map(ruleLabel);
  const joined =
    reasons.length > 1 ? `${reasons.slice(0, -1).join(", ")} and ${reasons.at(-1)}` : reasons[0];
  return (
    `${plural(rows.length, "record")}${sources.length ? ` from ${sources.join(" and ")}` : ""} ` +
    `were combined into one ${entityType.toLowerCase()} because they share ${joined}.`
  );
}

export function formatDate(d: string | null | undefined): string {
  if (!d) return "unknown";
  const date = new Date(d);
  return Number.isNaN(date.getTime())
    ? d
    : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function dateRange(first: string | null, last: string | null): string {
  if (!first && !last) return "dates unknown";
  if (first === last || !last) return formatDate(first);
  return `${formatDate(first)} to ${formatDate(last)}`;
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${plural(Math.floor(s / 60), "minute")} ago`;
  if (s < 86400) return `${plural(Math.floor(s / 3600), "hour")} ago`;
  return `${plural(Math.floor(s / 86400), "day")} ago`;
}

/** One sentence describing why a line on the canvas exists. */
export function edgeSentence(edge: GraphEdge, nodes: Map<string, GraphNode>): string {
  const a = nodes.get(edge.source)?.label ?? edge.source;
  const b = nodes.get(edge.target)?.label ?? edge.target;
  switch (edge.type) {
    case "HAS_ATTRIBUTE": {
      const type = String(edge.data.attr_type ?? "");
      return `${a} has ${lower(attrLabel(type))} ${b}.`;
    }
    case "RELATED_TO":
      return `${a} is linked to ${b} as ${String(edge.data.rel_type ?? "related").replace(/_/g, " ")}.`;
    case "ALIAS_OF":
      return `${a} and ${b} look like the same person (${String(edge.data.reason ?? "name variant")}).`;
    case "SHARES":
      return `${a} and ${b} share the same ${lower(attrLabel(String(edge.data.attr_type ?? "")))}.`;
    case "RESOLVED_TO":
      return `Source record ${a} was merged into ${b}.`;
    default:
      return `${a} is linked to ${b}.`;
  }
}

export function initials(subject: string): string {
  const name = subject.split("@")[0];
  const parts = name.split(/[._-]/).filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2)).toUpperCase();
}

export function roleLabel(role: string): string {
  return role.replace(/_/g, " ");
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usdExact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** "$1,234,567" for totals, "$1,234.50" for a single amount. */
export const money = (n: number, exact = false) => (exact ? usdExact : usd).format(n);
