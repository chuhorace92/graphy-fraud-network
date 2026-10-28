import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "../../api/client";
import type { CaseClaim } from "../../api/types";
import { formatDate, money, plural } from "../../lib/friendly";
import { Icon } from "../../ui/Icon";
import { Chip, EmptyState, ErrorNote, Skeleton, Stat } from "../../ui/kit";
import type { TabProps } from "./shared";

type SortKey = "claim" | "loss_date" | "fnol_date" | "amount" | "status" | "siu";

const COLUMNS: { key: SortKey | "type" | "people" | "detail"; label: string; numeric?: boolean; sortable: boolean }[] = [
  { key: "claim", label: "Claim", sortable: true },
  { key: "loss_date", label: "Loss", sortable: true },
  { key: "fnol_date", label: "Filed", sortable: true },
  { key: "type", label: "Type", sortable: false },
  { key: "amount", label: "Amount", numeric: true, sortable: true },
  { key: "status", label: "Status", sortable: true },
  { key: "siu", label: "SIU", sortable: true },
  { key: "people", label: "People", sortable: false },
  { key: "detail", label: "Detail", sortable: false },
];

/** How far a claim got through SIU: nothing, referred, accepted, or an outcome. */
const siuStep = (c: CaseClaim) => (c.siu_outcome ? 3 : c.siu_accepted ? 2 : c.siu_referred ? 1 : 0);

function Siu({ c }: { c: CaseClaim }) {
  if (c.siu_outcome) return <Chip tone="bad" title="The SIU outcome">SIU: {c.siu_outcome}</Chip>;
  if (c.siu_accepted) return <Chip tone="warn">Accepted by SIU</Chip>;
  if (c.siu_referred) return <Chip tone="accent">Referred to SIU</Chip>;
  return <span className="muted">–</span>;
}

/** Every claim in the case with what is on file for it and who is on it. */
export function ClaimsTab({ caseKey }: TabProps) {
  const claims = useQuery({ queryKey: ["case-claims", caseKey], queryFn: () => api.caseClaims(caseKey) });
  const [status, setStatus] = useState("");
  const [siuOnly, setSiuOnly] = useState(false);
  const [text, setText] = useState("");
  const [sort, setSort] = useState<SortKey>("loss_date");
  const [descending, setDescending] = useState(true);

  const items = useMemo(() => claims.data?.items ?? [], [claims.data]);
  const statuses = useMemo(() => {
    const c = new Map<string, number>();
    for (const x of items) c.set(x.status ?? "", (c.get(x.status ?? "") ?? 0) + 1);
    return [...c.entries()].filter(([k]) => k).sort();
  }, [items]);
  const rows = useMemo(() => {
    const q = text.trim().toLowerCase();
    const list = items.filter(
      (c) =>
        (!status || (c.status ?? "") === status) &&
        (!siuOnly || c.siu_referred) &&
        (!q ||
          c.claim.toLowerCase().includes(q) ||
          (c.description ?? "").toLowerCase().includes(q) ||
          c.parties.some((p) => p.label.toLowerCase().includes(q))),
    );
    const sign = descending ? -1 : 1;
    const key = (c: CaseClaim): string | number =>
      sort === "amount" ? (c.amount ?? -1) : sort === "siu" ? siuStep(c) : (c[sort] ?? "");
    return list.sort((a, b) => {
      const x = key(a), y = key(b);
      return sign * (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y)));
    });
  }, [items, status, siuOnly, text, sort, descending]);

  const sortBy = (k: SortKey) => {
    if (k === sort) setDescending(!descending);
    else {
      setSort(k);
      setDescending(k !== "claim" && k !== "status");
    }
  };

  if (claims.isPending) return <Skeleton rows={6} />;
  if (claims.isError) return <ErrorNote error={claims.error} />;
  if (items.length === 0) {
    return (
      <EmptyState icon="file" title="No claims in this case">
        This network has no claim records.
      </EmptyState>
    );
  }
  const total = rows.reduce((t, c) => t + (c.amount ?? 0), 0);
  const referred = rows.filter((c) => c.siu_referred).length;
  return (
    <div className="claims-tab">
      <div className="stats">
        <Stat value={rows.length.toLocaleString()} label={rows.length === items.length ? "claims" : "matching"} />
        <Stat value={money(total)} label="claimed" />
        <Stat value={referred} label="referred to SIU" />
        <Stat value={rows.filter((c) => c.siu_outcome).length} label="with an SIU outcome" />
      </div>

      <div className="po-statuses" role="group" aria-label="Filter by status">
        <button type="button" className={`chip chip-btn${status === "" ? " on" : ""}`} onClick={() => setStatus("")}>
          All {items.length}
        </button>
        {statuses.map(([s, n]) => (
          <button
            key={s}
            type="button"
            className={`chip chip-btn${status === s ? " on" : ""}`}
            onClick={() => setStatus(status === s ? "" : s)}
          >
            {s} {n}
          </button>
        ))}
        <button type="button" className={`chip chip-btn${siuOnly ? " on" : ""}`} onClick={() => setSiuOnly(!siuOnly)}>
          Referred to SIU
        </button>
      </div>

      <div className="toolbar">
        <label className="search-box">
          <Icon name="search" size={15} />
          <input
            type="search"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Search claim number, detail or a person…"
            aria-label="Search claims"
          />
        </label>
      </div>

      <table className="data claims-table">
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th
                key={c.key}
                className={c.numeric ? "num" : ""}
                aria-sort={c.sortable && c.key === sort ? (descending ? "descending" : "ascending") : "none"}
              >
                {c.sortable ? (
                  <button type="button" className="th-btn" onClick={() => sortBy(c.key as SortKey)}>
                    {c.label}
                    {c.key === sort && <Icon name={descending ? "chevronDown" : "chevronUp"} size={13} />}
                  </button>
                ) : (
                  c.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.entity_id}>
              <td className="nowrap">
                <strong>{c.claim}</strong>
              </td>
              <td className="nowrap">{c.loss_date ? formatDate(c.loss_date) : <span className="muted">–</span>}</td>
              <td className="nowrap">{c.fnol_date ? formatDate(c.fnol_date) : <span className="muted">–</span>}</td>
              <td>
                {c.loss_types.length ? (
                  <span className="holders">
                    {c.loss_types.map((t) => (
                      <span key={t} className="holder">
                        {t}
                      </span>
                    ))}
                  </span>
                ) : (
                  <span className="muted">–</span>
                )}
              </td>
              <td className="num">{c.amount != null ? money(c.amount, true) : <span className="muted">–</span>}</td>
              <td>{c.status ?? <span className="muted">–</span>}</td>
              <td>
                <Siu c={c} />
              </td>
              <td className="claim-people">
                {c.parties.length ? (
                  <>
                    {c.parties.slice(0, 4).map((p) => (
                      <div key={`${p.entity_id}-${p.role}`}>
                        {p.label} <span className="muted small">{p.role.replace(/_/g, " ")}</span>
                      </div>
                    ))}
                    {c.parties.length > 4 && <span className="muted small">and {plural(c.parties.length - 4, "more")}</span>}
                  </>
                ) : (
                  <span className="muted">–</span>
                )}
              </td>
              <td className="po-detail-cell">{c.description ?? <span className="muted">–</span>}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={COLUMNS.length} className="muted">
                No claim matches.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {claims.data.total > items.length && (
        <p className="muted small">
          Showing the newest {items.length.toLocaleString()} of {claims.data.total.toLocaleString()} claims.
        </p>
      )}
    </div>
  );
}
