import { useEffect, useState } from "react";

import type { SearchHit } from "../api/types";
import { useCanvas } from "../state/canvasStore";
import { GlobalSearch } from "../components/GlobalSearch";
import { Icon, type IconName } from "../ui/Icon";
import type { AlignMode, GraphView, KindStat } from "./GraphView";

const ALIGN: { mode: AlignMode; icon: IconName; title: string }[] = [
  { mode: "left", icon: "alignLeft", title: "Align left edges" },
  { mode: "hcenter", icon: "alignHCenter", title: "Align horizontal centres (one column)" },
  { mode: "right", icon: "alignRight", title: "Align right edges" },
  { mode: "top", icon: "alignTop", title: "Align top edges" },
  { mode: "vcenter", icon: "alignVCenter", title: "Align vertical centres (one row)" },
  { mode: "bottom", icon: "alignBottom", title: "Align bottom edges" },
];

const TIERS: { tier: 1 | 2; title: string; hint: string }[] = [
  { tier: 1, title: "Tier 1 · Connected items", hint: "People, claims, policies, vehicles and providers" },
  { tier: 2, title: "Tier 2 · Details", hint: "Addresses, phones, accounts and source records" },
];

/** Align and distribute the selected nodes, and collapse or expand whole kinds of node. */
export function CanvasToolkit({
  view,
  onAddEntity,
  anchorLabel,
  version = 0,
}: {
  view: GraphView | null;
  /** Add an entity from the database to the canvas. */
  onAddEntity?: (hit: SearchHit) => void;
  /** What a newly added entity is linked back to, for the hint under the search box. */
  anchorLabel?: string;
  /** Changes whenever nodes are added, so "find" can pick up the new ones. */
  version?: number;
}) {
  const [selected, setSelected] = useState(0);
  const [boxSelect, setBoxSelect] = useState(true);
  const [stats, setStats] = useState<KindStat[]>([]);
  const refresh = () => setStats(view?.kindStats() ?? []);

  // Find on graph: highlight every node whose label has all the typed words, then step through.
  const setFound = useCanvas((s) => s.setFound);
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<string[]>([]);
  const [at, setAt] = useState(-1);
  useEffect(() => {
    const ids = query.trim() ? (view?.find(query) ?? []) : [];
    setMatches(ids);
    setFound(ids);
    setAt(-1);
  }, [query, view, version, setFound]);
  useEffect(() => () => setFound([]), [setFound]);
  const step = (by: number) => {
    if (matches.length === 0) return;
    const i = (at + by + matches.length) % matches.length;
    setAt(i);
    view?.reveal(matches[i]);
  };

  useEffect(() => view?.onSelectionCount(setSelected), [view]);
  useEffect(() => view?.setBoxSelect(boxSelect), [view, boxSelect]);

  const toggle = (keys: string[], hidden: boolean) => {
    keys.forEach((k) => view?.setKindHidden(k, hidden));
    refresh();
  };

  return (
    <div className="toolkit" role="toolbar" aria-label="Arrange and collapse">
      <div className="toolkit-group" role="group" aria-label="Drag mode">
        <button type="button" className={boxSelect ? "on" : ""} aria-pressed={boxSelect}
                title="Drag to draw a box and select several nodes" onClick={() => setBoxSelect(true)}>
          <Icon name="select" />
        </button>
        <button type="button" className={boxSelect ? "" : "on"} aria-pressed={!boxSelect}
                title="Drag to move the view" onClick={() => setBoxSelect(false)}>
          <Icon name="pan" />
        </button>
      </div>
      <div className="toolkit-group" role="group" aria-label="Align">
        {ALIGN.map((a) => (
          <button key={a.mode} type="button" title={a.title} aria-label={a.title}
                  disabled={selected < 2} onClick={() => view?.align(a.mode)}>
            <Icon name={a.icon} />
          </button>
        ))}
        <button type="button" title="Space evenly across" aria-label="Distribute horizontally"
                disabled={selected < 3} onClick={() => view?.distribute("horizontal")}>
          <Icon name="distributeH" />
        </button>
        <button type="button" title="Space evenly down" aria-label="Distribute vertically"
                disabled={selected < 3} onClick={() => view?.distribute("vertical")}>
          <Icon name="distributeV" />
        </button>
      </div>
      <span className="toolkit-hint">
        {selected >= 2 ? `${selected} selected` : (boxSelect ? "Drag a box to select" : "Shift-drag to select several")}
      </span>

      <details className="toolkit-menu" onToggle={(e) => !e.currentTarget.open && setQuery("")}>
        <summary>
          <Icon name="target" size={16} /> Find on graph
        </summary>
        <div className="toolkit-panel toolkit-find">
          <div className="find-row">
            <input
              autoFocus
              value={query}
              placeholder="Type a name, claim number or detail…"
              aria-label="Find on the graph"
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  step(e.shiftKey ? -1 : 1);
                } else if (e.key === "Escape") setQuery("");
              }}
            />
            <button type="button" title="Previous match (Shift+Enter)" aria-label="Previous match"
                    disabled={matches.length === 0} onClick={() => step(-1)}>
              <Icon name="chevronUp" size={16} />
            </button>
            <button type="button" title="Next match (Enter)" aria-label="Next match"
                    disabled={matches.length === 0} onClick={() => step(1)}>
              <Icon name="chevronDown" size={16} />
            </button>
          </div>
          <p>
            {!query.trim()
              ? "Highlights matching nodes already on the graph and dims the rest. Every word you type must match, so “chris smith” also finds Christopher Smith."
              : matches.length === 0
                ? "Nothing on the graph matches. Use Add entity to bring it in from the database."
                : `${at >= 0 ? `${at + 1} of ` : ""}${matches.length} ${matches.length === 1 ? "match" : "matches"}. Enter for the next one.`}
          </p>
        </div>
      </details>

      {onAddEntity && (
        <details className="toolkit-menu">
          <summary>
            <Icon name="search" size={16} /> Add entity
          </summary>
          <div className="toolkit-panel toolkit-search">
            <GlobalSearch
              onPick={onAddEntity}
              shortcut={false}
              autoFocus
              placeholder="Search a person, company, claim, address, ID…"
            />
            <p>
              Adds the match with its connections, and looks for a path back to{" "}
              <strong>{anchorLabel ?? "the starting point"}</strong> to show how they are related.
              Select a different entity first to link to that one instead.
            </p>
          </div>
        </details>
      )}

      <details className="toolkit-menu" onToggle={(e) => e.currentTarget.open && refresh()}>
        <summary>
          <Icon name="layers" size={16} /> Collapse / expand
        </summary>
        <div className="toolkit-panel">
          {TIERS.map(({ tier, title, hint }) => {
            const rows = stats.filter((s) => s.tier === tier);
            const keys = rows.map((r) => r.key);
            return (
              <section key={tier}>
                <header>
                  <strong>{title}</strong>
                  <span>
                    <button type="button" onClick={() => toggle(keys, true)} disabled={!rows.length}>
                      Collapse all
                    </button>
                    <button type="button" onClick={() => toggle(keys, false)} disabled={!rows.length}>
                      Expand all
                    </button>
                  </span>
                </header>
                <p>{hint}</p>
                {rows.length === 0 && <p className="toolkit-empty">None on the canvas.</p>}
                {rows.map((r) => (
                  <label key={r.key}>
                    <input type="checkbox" checked={!r.hidden}
                           onChange={(e) => toggle([r.key], !e.target.checked)} />
                    <img src={r.icon} alt="" width={16} height={16} />
                    <span>{r.label}</span>
                    <em>{r.count}</em>
                  </label>
                ))}
              </section>
            );
          })}
          <button type="button" className="toolkit-all"
                  onClick={() => toggle(stats.map((s) => s.key), false)}>
            Expand everything
          </button>
        </div>
      </details>
    </div>
  );
}
