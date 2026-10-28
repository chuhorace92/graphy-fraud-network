import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import { api, type AttributeMode } from "../api/client";
import type { GraphData, GraphEdge, GraphNode, SearchHit } from "../api/types";
import { Badge } from "../graph/Badge";
import { GraphCanvas } from "../graph/GraphCanvas";
import type { GraphView, LayoutName } from "../graph/GraphView";
import { visualKey } from "../graph/icons";
import { plural } from "../lib/friendly";
import { useCanvas } from "../state/canvasStore";
import { Icon } from "../ui/Icon";
import { Chip, ErrorNote, Segmented } from "../ui/kit";
import { Inspector } from "./Inspector";

const LAYOUT_NAMES: { value: LayoutName; label: string }[] = [
  { value: "force", label: "Organic" },
  { value: "hierarchical", label: "Tree" },
  { value: "concentric", label: "Rings" },
];

const EMPTY: GraphData = { nodes: [], edges: [], truncated: false };
const NONE: GraphData[] = [];

/** An empty workbench until an entity is opened (`?entity=`) or added from the toolkit. */
export function InvestigationPage() {
  const [params] = useSearchParams();
  const root = params.get("entity");
  const saved = useCanvas((s) => s.search);
  // The nav link carries no entity: pick up where the last investigation left off.
  if (!root && new URLSearchParams(saved).has("entity")) return <Navigate to={{ search: saved }} replace />;
  // Keyed on the entity so every state resets cleanly when you open a different one.
  return <Workspace key={root ?? ""} root={root} />;
}

function Workspace({ root }: { root: string | null }) {
  const [params, setParams] = useSearchParams();
  const hops = Math.min(3, Math.max(1, Number(params.get("hops")) || 1));
  const attributes = (params.get("attrs") as AttributeMode) || "shared";
  const asked = params.get("layout");
  const layout = LAYOUT_NAMES.find((l) => l.value === asked)?.value ?? "force"; // old links may say "circular"
  const update = (patch: Record<string, string>) =>
    setParams(
      (p) => {
        Object.entries(patch).forEach(([k, v]) => p.set(k, v));
        return p;
      },
      { replace: true },
    );

  const qc = useQueryClient();
  const { selection, addExpansion, begin, clear, setSearch, setHighlighted } = useCanvas();
  const key = root ? `${root}|${hops}|${attributes}` : "";
  // Expansions outlive the page, but only count while they belong to this view.
  const expansions = useCanvas((s) => (s.owner === key ? s.expansions : NONE));
  const view = useRef<GraphView | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [expanding, setExpanding] = useState<string | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => begin(key), [key, begin]);
  useEffect(() => setSearch(params.toString()), [params, setSearch]);

  const graph = useQuery({
    queryKey: ["neighborhood", root, hops, attributes],
    queryFn: () => api.neighborhood(root!, hops, attributes),
    enabled: !!root,
  });

  // Base graph plus everything expanded since, de-duplicated by id (first one wins).
  const merged = useMemo(() => {
    const nodes = new Map<string, GraphNode>();
    const edges = new Map<string, GraphEdge>();
    for (const g of [graph.data, ...expansions]) {
      for (const n of g?.nodes ?? []) if (!nodes.has(n.id)) nodes.set(n.id, n);
      for (const e of g?.edges ?? []) if (!edges.has(e.id)) edges.set(e.id, e);
    }
    return { nodes, edges };
  }, [graph.data, expansions]);

  const nodesRef = useRef(merged.nodes);
  nodesRef.current = merged.nodes;

  const flash = useCallback((text: string) => {
    setNotice(text);
    clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), 5000);
  }, []);

  const expand = useCallback(
    async (node: GraphNode) => {
      if (node.kind !== "Entity") return;
      setExpanding(node.id);
      try {
        const g = await qc.fetchQuery({
          queryKey: ["neighborhood", node.id, 1, attributes],
          queryFn: () => api.neighborhood(node.id, 1, attributes),
        });
        const fresh = g.nodes.filter((n) => !nodesRef.current.has(n.id));
        if (fresh.length === 0) {
          flash(`Nothing new: everything ${node.label} is connected to is already shown.`);
        } else {
          addExpansion(g);
          const e = fresh.filter((n) => n.kind === "Entity").length;
          const a = fresh.filter((n) => n.kind === "AttributeValue").length;
          const parts: string[] = [];
          if (e) parts.push(plural(e, "connection"));
          if (a) parts.push(plural(a, "shared detail"));
          flash(`Added ${parts.join(" and ") || plural(fresh.length, "item")}.`);
        }
      } catch {
        flash("Couldn't load connections. Try again.");
      } finally {
        setExpanding(null);
      }
    },
    [qc, attributes, addExpansion, flash],
  );

  // Add any entity from the database: its connections, plus a path back to the selected entity
  // (or the starting point) so the relationship between them shows up.
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const pendingReveal = useRef<string | null>(null);
  const addEntity = useCallback(
    async (hit: SearchHit) => {
      if (nodesRef.current.has(hit.entity_id)) {
        view.current?.reveal(hit.entity_id);
        flash(`${hit.label} is already on the canvas.`);
        return;
      }
      const sel = selectionRef.current;
      const anchor =
        sel?.kind === "node" && sel.node.kind === "Entity" ? sel.node : root ? nodesRef.current.get(root) : undefined;
      const anchorId = anchor?.id ?? root;
      try {
        const [near, path] = await Promise.all([
          qc.fetchQuery({
            queryKey: ["neighborhood", hit.entity_id, 1, attributes],
            queryFn: () => api.neighborhood(hit.entity_id, 1, attributes),
          }),
          anchorId ? api.path(hit.entity_id, anchorId).catch(() => null) : null,
        ]);
        addExpansion(near);
        const steps = path ? path.nodes.length - 1 : 0;
        if (path && steps > 0) addExpansion(path);
        pendingReveal.current = hit.entity_id;
        const to = anchor?.label ?? "the starting point";
        flash(
          !anchorId
            ? `Added ${hit.label}.`
            : steps > 0
            ? `Added ${hit.label}. Linked to ${to} in ${plural(steps, "step")}.`
            : `Added ${hit.label}. No link to ${to} found.`,
        );
      } catch {
        flash("Couldn't add that entity. Try again.");
      }
    },
    [qc, attributes, addExpansion, flash, root],
  );

  // Once the canvas has merged the new nodes, select and centre the one just added.
  useEffect(() => {
    const id = pendingReveal.current;
    if (id && nodesRef.current.has(id)) {
      pendingReveal.current = null;
      view.current?.reveal(id);
    }
  }, [expansions]);

  // Double-click and the button share one handler; the ref keeps the canvas callback current.
  const expandRef = useRef(expand);
  expandRef.current = expand;

  // Selecting a shared detail lights up everyone who holds it.
  useEffect(() => {
    if (selection?.kind === "node" && selection.node.kind === "AttributeValue") {
      const id = selection.node.id;
      const ids = [id];
      for (const e of merged.edges.values()) if (e.target === id) ids.push(e.source);
      setHighlighted(ids);
    } else {
      setHighlighted([]);
    }
  }, [selection, merged.edges, setHighlighted]);

  // Esc clears the selection.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !(e.target as HTMLElement).closest("input, select, textarea")) {
        view.current?.select(null);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const exportPng = async () => {
    if (!view.current) return;
    const url = URL.createObjectURL(await view.current.exportPng());
    const a = Object.assign(document.createElement("a"), { href: url, download: `${root ?? "workbench"}.png` });
    a.click();
    URL.revokeObjectURL(url);
  };

  const focusNode = root ? merged.nodes.get(root) : undefined;
  const entityCount = [...merged.nodes.values()].filter((n) => n.kind === "Entity").length;
  const detailCount = [...merged.nodes.values()].filter((n) => n.kind === "AttributeValue").length;

  return (
    <div className="workspace">
      <div className="inv-bar">
        <div className="focus">
          {focusNode && <Badge k={visualKey(focusNode)} size={34} />}
          <div>
            <span className="eyebrow">{root ? "Investigating" : "Workbench"}</span>
            <strong>{root ? (focusNode?.label ?? "…") : "Add a person, company or claim to start"}</strong>
          </div>
        </div>

        <div className="ctl">
          <span className="ctl-label" title="How many links away from the starting point to include">
            Reach
          </span>
          <Segmented
            label="Reach"
            value={String(hops)}
            onChange={(v) => update({ hops: v })}
            options={[
              { value: "1", label: "1", hint: "Direct connections only" },
              { value: "2", label: "2", hint: "Connections of connections" },
              { value: "3", label: "3", hint: "Three links away" },
            ]}
          />
        </div>
        <div className="ctl">
          <span className="ctl-label">Show</span>
          <Segmented
            label="Which details to show"
            value={attributes}
            onChange={(v) => update({ attrs: v })}
            options={[
              { value: "shared", label: "Key links", hint: "Details held by two or more, plus everything the starting point has" },
              { value: "all", label: "Everything", hint: "Every detail of every person and company" },
              { value: "none", label: "People only", hint: "Hide details; draw lines between people directly" },
            ]}
          />
        </div>
        <div className="ctl">
          <span className="ctl-label">Layout</span>
          <Segmented
            label="Layout"
            value={layout}
            onChange={(v) => update({ layout: v })}
            options={LAYOUT_NAMES}
          />
        </div>

        <div className="bar-end">
          {graph.data?.truncated && (
            <Chip tone="warn" title="Only the first part of this network is shown">
              Partial view
            </Chip>
          )}
          {merged.nodes.size > 0 && (
            <button
              type="button"
              className="btn"
              onClick={() => {
                clear();
                setParams(new URLSearchParams());
              }}
            >
              Clear
            </button>
          )}
          <button type="button" className="btn" onClick={exportPng} disabled={merged.nodes.size === 0}>
            <Icon name="download" size={16} /> Export image
          </button>
        </div>
      </div>

      <div className="inv-body">
        <GraphCanvas
          base={root ? graph.data : EMPTY}
          expansions={expansions}
          layout={layout}
          focus={root ?? undefined}
          onAddEntity={addEntity}
          anchorLabel={
            selection?.kind === "node" && selection.node.kind === "Entity"
              ? selection.node.label
              : focusNode?.label
          }
          onReady={(v) => {
            view.current = v;
            v.onActivate((n) => expandRef.current(n));
          }}
        >
          {!root && entityCount === 0 && (
            <div className="overlay empty">
              <strong>Find a network</strong>
              <span>
                Search for a person, company, claim, address, phone, email or ID, or open{" "}
                <strong>Add entity</strong> on the canvas toolbar. Press <kbd>/</kbd> to search from anywhere.
              </span>
            </div>
          )}
          {root && graph.isPending && <div className="overlay">Loading network…</div>}
          {graph.isError && (
            <div className="overlay">
              <ErrorNote error={graph.error} />
            </div>
          )}
          {root && graph.isSuccess && entityCount === 1 && detailCount <= 7 && (
            <div className="overlay hint">
              No one else shares a detail with {focusNode?.label}. Try <strong>Everything</strong> to see all their details.
            </div>
          )}
          {notice && (
            <div className="toast" role="status">
              {notice}
            </div>
          )}
        </GraphCanvas>

        <aside className="inspector" aria-label="Details">
          <Inspector
            selection={selection}
            nodes={merged.nodes}
            edges={merged.edges}
            focus={root ?? ""}
            truncated={!!graph.data?.truncated}
            expanding={expanding}
            onExpand={expand}
            onReveal={(id) => view.current?.reveal(id)}
            onClear={() => view.current?.select(null)}
          />
        </aside>
      </div>
    </div>
  );
}
