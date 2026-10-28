import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../api/client";
import type { GraphData, GraphEdge, GraphNode } from "../../api/types";
import { GraphCanvas } from "../../graph/GraphCanvas";
import type { GraphView } from "../../graph/GraphView";
import { plural } from "../../lib/friendly";
import { useCanvas } from "../../state/canvasStore";
import { Icon } from "../../ui/Icon";
import { Chip, ErrorNote } from "../../ui/kit";
import { Inspector } from "../Inspector";
import type { TabProps } from "./shared";

/** The case's network drawn in place, with the panel that explains whatever is clicked. */
export function NetworkTab({ detail }: TabProps) {
  const focus = detail.summary.focus_id;
  const qc = useQueryClient();
  const selection = useCanvas((s) => s.selection);
  const setHighlighted = useCanvas((s) => s.setHighlighted);
  const [expanded, setExpanded] = useState(false);
  const [extras, setExtras] = useState<GraphData[]>([]);
  const [expanding, setExpanding] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const view = useRef<GraphView | null>(null);
  const seen = useRef(new Set<string>());
  const graph = useQuery({
    queryKey: ["neighborhood", focus, 3, "shared"],
    queryFn: () => api.neighborhood(focus, 3, "shared"),
  });

  // What is on the canvas: the network plus everything revealed since, by id.
  const merged = useMemo(() => {
    const nodes = new Map<string, GraphNode>();
    const edges = new Map<string, GraphEdge>();
    for (const g of [graph.data, ...extras]) {
      for (const n of g?.nodes ?? []) if (!nodes.has(n.id)) nodes.set(n.id, n);
      for (const e of g?.edges ?? []) if (!edges.has(e.id)) edges.set(e.id, e);
    }
    return { nodes, edges };
  }, [graph.data, extras]);

  // Add whoever else a provider is connected to (double-click, or the panel's button).
  const reveal = async (node: GraphNode) => {
    if (node.kind !== "Entity" || seen.current.has(node.id)) return;
    seen.current.add(node.id);
    setExpanding(node.id);
    try {
      const g = await qc.fetchQuery({
        queryKey: ["neighborhood", node.id, 1, "shared"],
        queryFn: () => api.neighborhood(node.id, 1, "shared"),
      });
      const fresh = g.nodes.filter((n) => !merged.nodes.has(n.id));
      if (fresh.length === 0) setNote(`Nothing new: everything ${node.label} is connected to is already shown.`);
      else {
        setExtras((cur) => [...cur, g]);
        setNote(`Added ${plural(fresh.length, "item")}.`);
      }
    } catch {
      seen.current.delete(node.id);
      setNote("Couldn't load connections. Try again.");
    } finally {
      setExpanding(null);
    }
  };
  const revealRef = useRef(reveal);
  revealRef.current = reveal;
  useEffect(() => {
    if (!note) return;
    const t = setTimeout(() => setNote(null), 5000);
    return () => clearTimeout(t);
  }, [note]);

  // The canvas store is shared with Investigate: start from a clean selection, not its leftovers.
  useEffect(() => useCanvas.getState().clearView(), []);

  // Selecting a shared detail lights up everyone who holds it.
  useEffect(() => {
    if (selection?.kind === "node" && selection.node.kind === "AttributeValue") {
      const id = selection.node.id;
      setHighlighted([id, ...[...merged.edges.values()].filter((e) => e.target === id).map((e) => e.source)]);
    } else {
      setHighlighted([]);
    }
  }, [selection, merged.edges, setHighlighted]);

  // Esc folds the expanded view back; the canvas follows the new size.
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setExpanded(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [expanded]);
  useEffect(() => {
    const t = setTimeout(() => view.current?.fit(), 60);
    return () => clearTimeout(t);
  }, [expanded]);

  return (
    <div className={`case-network${expanded ? " expanded" : ""}`}>
      <div className="cn-bar">
        <span className="muted small">
          {plural(detail.summary.size, "provider")} · {plural(detail.summary.links, "link")}. Click anything to see why it
          is there; double-click a provider to reveal who else it connects to.
        </span>
        {graph.data?.truncated && <Chip tone="warn">Partial view</Chip>}
        <button type="button" className="btn small" onClick={() => setExpanded(!expanded)} aria-pressed={expanded}>
          <Icon name={expanded ? "close" : "expand"} size={15} /> {expanded ? "Close" : "Expand"}
        </button>
      </div>
      <div className="cn-body">
        <div className="cn-canvas">
          <GraphCanvas
            base={graph.data}
            expansions={extras}
            layout="force"
            focus={focus}
            onReady={(v) => {
              view.current = v;
              v.onActivate((n) => revealRef.current(n));
            }}
          >
            {graph.isPending && <div className="overlay">Loading network…</div>}
            {note && (
              <div className="toast" role="status">
                {note}
              </div>
            )}
            {graph.isError && (
              <div className="overlay">
                <ErrorNote error={graph.error} />
              </div>
            )}
          </GraphCanvas>
        </div>
        <aside className="cn-panel inspector" aria-label="Details">
          <Inspector
            selection={selection}
            nodes={merged.nodes}
            edges={merged.edges}
            focus={focus}
            truncated={!!graph.data?.truncated}
            expanding={expanding}
            onExpand={reveal}
            onReveal={(id) => view.current?.reveal(id)}
            onClear={() => view.current?.select(null)}
          />
        </aside>
      </div>
    </div>
  );
}
