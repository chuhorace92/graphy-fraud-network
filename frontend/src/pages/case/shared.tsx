import type { CaseDetail, CaseStatus, Outcome } from "../../api/types";

export const STATUSES: { value: CaseStatus; label: string; tone: "accent" | "warn" | "bad" | "neutral" | "good" }[] = [
  { value: "new", label: "New", tone: "accent" },
  { value: "investigating", label: "Investigating", tone: "warn" },
  { value: "confirmed", label: "Confirmed fraud", tone: "bad" },
  { value: "insufficient", label: "Not enough information", tone: "neutral" },
  { value: "dismissed", label: "Dismissed", tone: "good" },
];

/** How a case can end, with what each means. */
export const OUTCOMES: { value: Outcome; label: string; hint: string }[] = [
  { value: "confirmed", label: "Confirmed fraud", hint: "The evidence supports it" },
  { value: "insufficient", label: "Not enough information", hint: "Cannot say either way yet" },
  { value: "dismissed", label: "Dismissed", hint: "A legitimate explanation, or no fraud" },
];

export const statusOf = (s: CaseStatus) => STATUSES.find((x) => x.value === s)!;
export const isClosed = (s: CaseStatus) => s === "confirmed" || s === "insufficient" || s === "dismissed";

/** What every tab of a case receives. `saved` takes the case a change returns. */
export interface TabProps {
  caseKey: string;
  detail: CaseDetail;
  canAct: boolean;
  saved: (d: CaseDetail) => void;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  return n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
