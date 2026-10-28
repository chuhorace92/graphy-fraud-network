import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { CaseSummary } from "../api/types";
import { attrLabel, initials, lower, money, plural, relativeTime } from "../lib/friendly";
import { useMe } from "../lib/useMe";
import { Icon } from "../ui/Icon";
import { Chip, EmptyState, ErrorNote, Segmented, Skeleton, Stat } from "../ui/kit";
import { isClosed, statusOf } from "./case/shared";

type Queue = "open" | "mine" | "closed" | "all";
type SortKey = "score" | "case" | "size" | "claim_count" | "claimed_amount" | "open_tasks" | "status" | "updated_at";

const isOpen = (c: CaseSummary) => !isClosed(c.status);
const STATUS_ORDER = { new: 0, investigating: 1, confirmed: 2, insufficient: 3, dismissed: 4 };

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "score", label: "Score" },
  { key: "case", label: "Case" },
  { key: "size", label: "Entities", numeric: true },
  { key: "claim_count", label: "Claims", numeric: true },
  { key: "claimed_amount", label: "Claimed", numeric: true },
  { key: "open_tasks", label: "Open tasks", numeric: true },
  { key: "status", label: "Status" },
  { key: "updated_at", label: "Updated" },
];

const compare: Record<SortKey, (a: CaseSummary, b: CaseSummary) => number> = {
  score: (a, b) => a.score - b.score || a.size - b.size,
  case: (a, b) => a.focus_label.localeCompare(b.focus_label),
  size: (a, b) => a.size - b.size,
  claim_count: (a, b) => a.claim_count - b.claim_count,
  claimed_amount: (a, b) => a.claimed_amount - b.claimed_amount,
  open_tasks: (a, b) => a.open_tasks - b.open_tasks,
  status: (a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status],
  updated_at: (a, b) => (a.updated_at ?? "").localeCompare(b.updated_at ?? ""),
};

/** Case management: every network flagged by fraud indicators, as a table. A row opens its case. */
export function AnalyticsPage() {
  const { me } = useMe();
  const navigate = useNavigate();
  const [queue, setQueue] = useState<Queue>("open");
  const [severity, setSeverity] = useState("");
  const [text, setText] = useState("");
  const [sort, setSort] = useState<SortKey>("score");
  const [descending, setDescending] = useState(true);
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });

  const all = useMemo(() => cases.data ?? [], [cases.data]);
  const mineOpen = (c: CaseSummary) => isOpen(c) && !!me && c.assignee === me.subject;
  const counts: Record<Queue, number> = {
    open: all.filter(isOpen).length,
    mine: all.filter(mineOpen).length,
    closed: all.filter((c) => !isOpen(c)).length,
    all: all.length,
  };
  const shown = useMemo(() => {
    const q = text.trim().toLowerCase();
    const rows = all.filter(
      (c) =>
        (queue === "all" || (queue === "open" && isOpen(c)) || (queue === "mine" && mineOpen(c)) || (queue === "closed" && !isOpen(c))) &&
        (!severity || c.severity === severity) &&
        (!q || c.focus_label.toLowerCase().includes(q) || c.flags.some((f) => f.toLowerCase().includes(q))),
    );
    const sign = descending ? -1 : 1;
    return rows.sort((a, b) => sign * compare[sort](a, b));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, queue, severity, text, sort, descending, me]);

  const sortBy = (key: SortKey) => {
    if (key === sort) setDescending(!descending);
    else {
      setSort(key);
      setDescending(key !== "case");
    }
  };
  const openCases = all.filter(isOpen);
  const open = (c: CaseSummary) => navigate(`/analytics/${encodeURIComponent(c.case_key)}`);

  return (
    <div className="page wide">
      <header className="page-head">
        <div>
          <h1>Cases</h1>
          <p className="muted">
            Networks of people, claims and providers joined by roles, shared details or probable aliases,
            scored on fraud indicators. Open one to work it.
          </p>
        </div>
        <div className="stats overview">
          <Stat value={openCases.length} label="open cases" />
          <Stat value={openCases.filter((c) => c.severity === "high").length} label="high severity" />
          <Stat value={money(openCases.reduce((sum, c) => sum + c.claimed_amount, 0))} label="claimed" />
        </div>
      </header>

      <div className="toolbar">
        <Segmented
          label="Cases to show"
          value={queue}
          onChange={setQueue}
          options={[
            { value: "open", label: `Open ${counts.open}` },
            { value: "mine", label: `Mine ${counts.mine}` },
            { value: "closed", label: `Closed ${counts.closed}` },
            { value: "all", label: `All ${counts.all}` },
          ]}
        />
        <label className="search-box">
          <Icon name="search" size={16} />
          <input
            type="search"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Search by name, claim or reason…"
            aria-label="Search cases"
          />
        </label>
        <select value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Filter by severity">
          <option value="">All severities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <span className="muted small">{cases.data ? plural(shown.length, "case") : ""}</span>
      </div>

      {cases.isPending && <Skeleton rows={8} />}
      {cases.isError && <ErrorNote error={cases.error} />}
      {cases.isSuccess && all.length === 0 && (
        <EmptyState icon="network" title="No cases yet">
          Cases appear when people, claims and providers are linked by roles, shared details or aliases. Load the demo data with{" "}
          <code>make seed</code>, or upload a batch from the API.
        </EmptyState>
      )}
      {cases.isSuccess && all.length > 0 && shown.length === 0 && (
        <EmptyState icon="search" title="No cases match">
          Try another view or clear the search.
        </EmptyState>
      )}
      {shown.length > 0 && (
        <table className="data cases-table">
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  className={c.numeric ? "num" : ""}
                  aria-sort={c.key === sort ? (descending ? "descending" : "ascending") : "none"}
                >
                  <button type="button" className="th-btn" onClick={() => sortBy(c.key)}>
                    {c.label}
                    {c.key === sort && <Icon name={descending ? "chevronDown" : "chevronUp"} size={13} />}
                  </button>
                </th>
              ))}
              <th>Owner</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((c) => {
              const status = statusOf(c.status);
              const via = c.via.slice(0, 3).map((v) => lower(attrLabel(v)));
              return (
                <tr key={c.case_key} className={`case-tr sev-${c.severity}`} onClick={() => open(c)}>
                  <td>
                    <span className={`risk risk-${c.severity}`} title="Fraud indicators, 0 to 100">
                      <b>{c.score}</b>
                      {c.severity}
                    </span>
                  </td>
                  <td className="case-cell">
                    <Link
                      className="link-btn strong"
                      to={`/analytics/${encodeURIComponent(c.case_key)}`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {c.focus_label}
                      {c.size > 1 && <span className="muted"> + {c.size - 1}</span>}
                    </Link>
                    <div className="muted small">
                      {via.length > 0 ? `Linked by ${via.join(", ")}` : "Nothing shared"}
                      {c.flags[0] && <> · {c.flags[0]}</>}
                    </div>
                  </td>
                  <td className="num">{c.size}</td>
                  <td className="num">{c.claim_count}</td>
                  <td className="num">{money(c.claimed_amount)}</td>
                  <td className="num">{c.open_tasks > 0 ? c.open_tasks : <span className="muted">–</span>}</td>
                  <td>
                    <Chip tone={status.tone}>{status.label}</Chip>
                  </td>
                  <td className="muted">{c.updated_at ? relativeTime(c.updated_at) : "–"}</td>
                  <td>
                    {c.assignee ? (
                      <span className="owner" title={c.assignee}>
                        <span className="owner-dot">{initials(c.assignee)}</span>
                        <span className="small">{me && c.assignee === me.subject ? "You" : c.assignee.split("@")[0]}</span>
                      </span>
                    ) : (
                      <span className="muted">–</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
