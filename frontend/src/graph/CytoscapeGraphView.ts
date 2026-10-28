import cytoscape, {
  type Core,
  type ElementDefinition,
  type LayoutOptions,
  type StylesheetJson,
} from "cytoscape";
import fcose from "cytoscape-fcose";

import type { GraphData, GraphEdge, GraphNode } from "../api/types";
import type { AlignMode, GraphView, HoverInfo, KindStat, LayoutName, Selection } from "./GraphView";
import { ROLE_ORDER, VISUALS, badgeUri, entityKey, glyphUri, siuGlyphUri, visualKey } from "./icons";

cytoscape.use(fcose);

const FIT_PADDING = 48;
const ALIAS_RED = "#E02424";

/** How far apart the layout tries to keep the two ends of a link. Everything that belongs to a
 *  claim (its roles, policy and vehicle) is short, so each claim keeps its own cluster. */
const LINK_LENGTH: Record<string, number> = {
  insured: 55, claimant: 55, witness: 60, driver: 55, passenger: 55,
  under_policy: 45, involves: 45, policyholder: 80, owner: 80,
  represents: 100, treated_for: 100, repaired_for: 100,
};
const linkLength = (edge: cytoscape.EdgeSingular): number => {
  switch (edge.data("type")) {
    case "HAS_ATTRIBUTE":
      return 85;
    case "RELATED_TO":
      return LINK_LENGTH[edge.data("label") as string] ?? 120;
    case "ALIAS_OF":
      return 140;
    default:
      return 150;
  }
};
const MAX_FIT_ZOOM = 1.3; // a lone node should not fill the screen

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Layout options per name. `incremental` pins existing nodes and places only the new ones. */
function layoutOptions(
  name: LayoutName,
  focus: string | null,
  pinned: cytoscape.NodeCollection | null,
  claims: string[] = [],
): LayoutOptions {
  const common = { animate: false, fit: pinned === null, padding: FIT_PADDING };
  switch (name) {
    case "force":
      return {
        ...common,
        name: "fcose",
        // "proof" runs the full spring simulation: slower but far better separated.
        quality: pinned ? "default" : "proof",
        randomize: pinned === null,
        nodeDimensionsIncludeLabels: true,
        packComponents: true,
        nodeRepulsion: () => 14000,
        // Attribute nodes sit close to their holders; entity-to-entity links stand off further.
        idealEdgeLength: linkLength,
        // Short links are stiff, so the people on a claim stay beside it.
        edgeElasticity: (edge: cytoscape.EdgeSingular) => (linkLength(edge) <= 60 ? 0.9 : 0.4),
        nodeSeparation: 110,
        gravity: 0.3,
        gravityRange: 4,
        numIter: 3000,
        // Claims are the hub of every story, so they are fixed in a small ring at the centre
        // and everything else settles around them. An incremental layout pins what is placed.
        ...(pinned
          ? { fixedNodeConstraint: pinned.map((n) => ({ nodeId: n.id(), position: { ...n.position() } })) }
          : claims.length > 0 && {
              fixedNodeConstraint: claims.map((id, i) => {
                const r = claims.length === 1 ? 0 : Math.max(120, (200 * claims.length) / (2 * Math.PI));
                const a = (i / claims.length) * 2 * Math.PI;
                return { nodeId: id, position: { x: r * Math.cos(a), y: r * Math.sin(a) } };
              }),
            }),
      } as LayoutOptions;
    case "hierarchical":
      return {
        ...common,
        name: "breadthfirst",
        directed: false,
        roots: focus ? [focus] : undefined,
        spacingFactor: 1.15,
        avoidOverlap: true,
        nodeDimensionsIncludeLabels: true,
      } as LayoutOptions;
    case "concentric":
      // Focus in the middle, then entities, then records, with attributes on the outer ring.
      return {
        ...common,
        name: "concentric",
        avoidOverlap: true,
        nodeDimensionsIncludeLabels: true,
        minNodeSpacing: 30,
        concentric: (n: cytoscape.NodeSingular) =>
          n.data("entity_type") === "Claim"
            ? 10
            : n.id() === focus
              ? 9
              : { Entity: 6, Group: 6, SourceRecord: 4 }[n.data("kind") as string] ?? 2,
        levelWidth: () => 1,
      } as LayoutOptions;
  }
}

/** fcose lets its springs beat its overlap repulsion on dense graphs, so after it runs, push
 *  overlapping boxes (label included) apart along their shallowest axis. `pinned` nodes stay put. */
function separateOverlaps(cy: Core, pinned?: cytoscape.NodeCollection): void {
  const nodes = cy.nodes().filter((n) => !n.isParent() && n.visible()).toArray() as cytoscape.NodeSingular[];
  const items = nodes
    .map((n) => ({ n, b: { ...n.boundingBox({ includeLabels: true }) }, fixed: !!pinned?.contains(n), dx: 0, dy: 0 }));
  const GAP = 6;
  for (let pass = 0; pass < 80; pass++) {
    let moved = false;
    for (let i = 0; i < items.length; i++) {
      for (let j = i + 1; j < items.length; j++) {
        const a = items[i];
        const b = items[j];
        if ((a.fixed && b.fixed) || a.b.x1 >= b.b.x2 + GAP || b.b.x1 >= a.b.x2 + GAP) continue;
        const ox = Math.min(a.b.x2, b.b.x2) - Math.max(a.b.x1, b.b.x1) + GAP;
        const oy = Math.min(a.b.y2, b.b.y2) - Math.max(a.b.y1, b.b.y1) + GAP;
        if (ox <= 0 || oy <= 0) continue;
        moved = true;
        const horizontal = ox < oy;
        const [ca, cb] = horizontal ? [a.b.x1 + a.b.x2, b.b.x1 + b.b.x2] : [a.b.y1 + a.b.y2, b.b.y1 + b.b.y2];
        const push = (horizontal ? ox : oy) * (ca < cb ? -1 : 1); // away from the other box
        const share = a.fixed ? 0 : b.fixed ? 1 : 0.5;
        for (const [it, d] of [[a, push * share], [b, -push * (1 - share)]] as const) {
          if (horizontal) {
            it.b.x1 += d; it.b.x2 += d; it.dx += d;
          } else {
            it.b.y1 += d; it.b.y2 += d; it.dy += d;
          }
        }
      }
    }
    if (!moved) break;
  }
  cy.batch(() => {
    for (const { n, dx, dy } of items) if (dx || dy) n.position({ x: n.position("x") + dx, y: n.position("y") + dy });
  });
}

/** Does the segment p→q cross the box (Liang–Barsky)? */
function segmentHitsBox(
  p: { x: number; y: number }, q: { x: number; y: number },
  b: { x1: number; y1: number; x2: number; y2: number },
): boolean {
  let t0 = 0;
  let t1 = 1;
  const dx = q.x - p.x;
  const dy = q.y - p.y;
  for (const [d, lo] of [[-dx, p.x - b.x1], [dx, b.x2 - p.x], [-dy, p.y - b.y1], [dy, b.y2 - p.y]] as const) {
    if (d === 0) {
      if (lo < 0) return false;
    } else if (d < 0) {
      t0 = Math.max(t0, lo / d);
    } else {
      t1 = Math.min(t1, lo / d);
    }
  }
  return t0 <= t1;
}

/** Edges should not run through nodes they do not touch. A node sitting on someone else's edge
 *  is stepped sideways off it, towards the outside of the picture where there are fewer edges. */
function clearEdges(cy: Core, pinned?: cytoscape.NodeCollection): void {
  const nodes = cy.nodes().filter((n) => !n.isParent() && n.visible());
  const edges = cy.edges().filter((e) => e.visible()).toArray() as cytoscape.EdgeSingular[];
  const movable = nodes.filter((n) => n.data("entity_type") !== "Claim" && !pinned?.contains(n));
  const box = nodes.boundingBox();
  const centre = { x: (box.x1 + box.x2) / 2, y: (box.y1 + box.y2) / 2 };
  const STEP = 24;
  for (let pass = 0; pass < 12; pass++) {
    let moved = false;
    movable.forEach((n) => {
      const b = n.boundingBox({ includeLabels: true });
      const blocker = edges.find(
        (e) => e.source().id() !== n.id() && e.target().id() !== n.id()
          && segmentHitsBox(e.source().position(), e.target().position(), b),
      );
      if (!blocker) return;
      const [s, t, p] = [blocker.source().position(), blocker.target().position(), n.position()];
      const len = Math.hypot(t.x - s.x, t.y - s.y) || 1;
      let nx = -(t.y - s.y) / len; // unit normal to the edge
      let ny = (t.x - s.x) / len;
      if (nx * (p.x - centre.x) + ny * (p.y - centre.y) < 0) [nx, ny] = [-nx, -ny]; // the outer side
      n.position({ x: p.x + nx * STEP, y: p.y + ny * STEP });
      moved = true;
    });
    if (!moved) break;
  }
}

/** Colours come from the CSS theme tokens so the canvas follows light and dark mode. */
function stylesheet(): StylesheetJson {
  const fg = cssVar("--fg");
  const muted = cssVar("--muted");
  const bg = cssVar("--bg");
  const label = {
    label: "data(label)",
    color: fg,
    "text-valign": "bottom",
    "text-halign": "center",
    "text-margin-y": 5,
    "text-wrap": "ellipsis",
    "text-max-width": "120px",
    "text-background-color": bg,
    "text-background-opacity": 0.75,
    "text-background-padding": "2px",
    "text-background-shape": "roundrectangle",
    "min-zoomed-font-size": 7,
  } as const;
  return [
    {
      selector: "node",
      style: {
        ...label,
        "background-color": "data(color)",
        "background-image": "data(icon)",
        "background-fit": "none",
        "background-width": "62%",
        "background-height": "62%",
        "background-clip": "none",
        "border-width": 2,
        "border-color": bg,
        width: 28,
        height: 28,
        "font-size": 9,
        "font-family": "system-ui, -apple-system, sans-serif",
      },
    },
    {
      selector: "node.Entity",
      style: { width: 46, height: 46, "font-size": 11, "font-weight": 600, "border-width": 3 },
    },
    // Risk is a ring, so it never competes with the type colour for one visual channel.
    { selector: "node.Entity[score >= 50]", style: { "border-color": "#E69F00", "border-width": 4 } },
    { selector: "node.Entity[score >= 80]", style: { "border-color": "#D55E00", "border-width": 5 } },
    {
      selector: "node.focus",
      style: { width: 58, height: 58, "border-width": 5, "border-color": fg },
    },
    // The icon already contains the flag, drawn over the whole node so it lands on the rim.
    { selector: "node.siu", style: { "background-width": "100%", "background-height": "100%" } },
    { selector: "node.SourceRecord", style: { width: 24, height: 24, "font-size": 8 } },
    {
      selector: "node.AttributeValue[status = 'hub']",
      style: { width: 36, height: 36, "border-width": 3, "border-style": "dashed", "border-color": "#E0218A" },
    },
    {
      selector: ":parent",
      style: {
        "background-image": "none",
        "background-opacity": 0.06,
        "background-color": fg,
        "border-width": 1,
        "border-style": "dashed",
        "border-color": muted,
        "text-valign": "top",
        "font-weight": 700,
        padding: "16px",
        shape: "round-rectangle",
      },
    },
    {
      selector: "node.collapsed",
      style: { width: 44, height: 44, "background-image": "data(icon)", "background-opacity": 1 },
    },
    {
      selector: "edge",
      style: {
        width: 0.8,
        "line-color": "data(color)",
        "curve-style": "straight",
        opacity: 0.45,
      },
    },
    // A value no longer current: dotted, so history reads differently from today's links.
    { selector: "edge[?historic]", style: { "line-style": "dotted", opacity: 0.45 } },
    {
      selector: "edge.RELATED_TO",
      style: {
        width: 1.1,
        opacity: 0.7,
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        "target-arrow-color": "data(color)",
        "arrow-scale": 0.6,
      },
    },
    // Role links name the role on the line; an alias is the loudest line on the canvas.
    {
      selector: "edge.RELATED_TO",
      style: {
        label: "data(label)",
        "font-size": 8,
        "min-zoomed-font-size": 11, // role names appear once you zoom in
        color: fg,
        "text-rotation": "autorotate",
        "text-background-color": bg,
        "text-background-opacity": 0.8,
        "text-background-padding": "1px",
      },
    },
    {
      selector: "edge.ALIAS_OF",
      style: {
        width: 2.2,
        opacity: 1,
        "line-color": ALIAS_RED,
        "curve-style": "bezier",
        "z-index": 900,
      },
    },
    // The links of whatever is selected stand out from the rest.
    {
      selector: "edge.hot",
      style: { width: 2.2, opacity: 1, "z-index": 800, "min-zoomed-font-size": 0 },
    },
    { selector: "edge.RESOLVED_TO", style: { "line-style": "dashed", width: 1.2 } },
    {
      selector: ":selected",
      style: {
        "overlay-color": "#0072B2",
        "overlay-opacity": 0.22,
        "overlay-padding": 7,
        "text-max-width": "260px",
        "z-index": 999,
      },
    },
    { selector: ".dim", style: { opacity: 0.12 } },
    {
      selector: "node.hl",
      style: { opacity: 1, "border-width": 4, "border-color": "#D55E00" },
    },
  ];
}

/** A link takes the colour of what it carries: the attribute, or the role. */
function edgeColor(e: GraphEdge, fallback: string): string {
  const attr = e.data.attr_type;
  if (typeof attr === "string" && attr in VISUALS) return VISUALS[attr as keyof typeof VISUALS].color;
  const role = `role_${String(e.data.rel_type)}`;
  return e.type === "RELATED_TO" && role in VISUALS ? VISUALS[role as keyof typeof VISUALS].color : fallback;
}

function toElements(graph: GraphData, existing: Set<string>): ElementDefinition[] {
  const present = new Set([...existing, ...graph.nodes.map((n) => n.id)]);
  const line = cssVar("--muted");
  const nodes: ElementDefinition[] = graph.nodes
    .filter((n) => !existing.has(n.id))
    .map((n) => {
      const key = visualKey(n);
      const siu = n.data.siu === true;
      return {
        group: "nodes",
        classes: siu ? `${n.kind} siu` : n.kind,
        data: {
          id: n.id,
          label: n.label,
          kind: n.kind,
          entity_type: n.entity_type,
          score: n.score ?? 0,
          status: n.status,
          color: VISUALS[key].color,
          icon: siu ? siuGlyphUri(key) : glyphUri(key),
          parent: n.parent && present.has(n.parent) ? n.parent : undefined,
          raw: n,
        },
      };
    });
  const edges: ElementDefinition[] = graph.edges
    .filter((e) => !existing.has(e.id) && present.has(e.source) && present.has(e.target))
    .map((e) => {
      return {
        group: "edges",
        classes: e.type,
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          type: e.type,
          label: e.label ?? e.type,
          color: edgeColor(e, line),
          historic: e.data.is_current === false,
          raw: e,
        },
      };
    });
  return [...nodes, ...edges];
}

/** Lowercase, accent-free, single-spaced: "José  Núñez" and "jose nunez" compare equal. */
const fold = (text: string): string =>
  text.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().split(/\s+/).join(" ").trim();

/** Collapse/expand key for a node: its kind of entity, attribute type, or "record". */
function kindOf(n: cytoscape.NodeSingular): string | null {
  switch (n.data("kind")) {
    case "Entity":
      return `entity:${n.data("entity_type")}`;
    case "AttributeValue": {
      const t = (n.data("raw") as GraphNode).data.attr_type;
      return `attr:${typeof t === "string" ? t : "other"}`;
    }
    case "SourceRecord":
      return "record";
    default:
      return null; // groups fold with a double-click, not through the menu
  }
}

export class CytoscapeGraphView implements GraphView {
  private hiddenKinds = new Set<string>();
  private boxSelect = true;
  private selectionHandlers = new Set<(count: number) => void>();
  private cy: Core | null = null;
  private handlers = new Set<(s: Selection | null) => void>();
  private collapsed = new Set<string>();
  private focus: string | null = null;
  private hoverHandlers = new Set<(h: HoverInfo | null) => void>();
  private activateHandlers = new Set<(n: GraphNode) => void>();
  private resizeObserver: ResizeObserver | null = null;
  private themeObserver: MutationObserver | null = null;
  private colorScheme: MediaQueryList | null = null;
  private interacted = false;

  mount(container: HTMLElement): void {
    const cy = cytoscape({
      container,
      userPanningEnabled: !this.boxSelect,
      style: stylesheet(),
      minZoom: 0.05,
      maxZoom: 4,
      boxSelectionEnabled: true, // shift-drag a box; plain drag still pans
      wheelSensitivity: 0.25,
    });
    this.cy = cy;

    cy.on("tap", (evt) => {
      const target = evt.target;
      if (target === cy) return this.emit(null);
      if (target.isNode()) return this.emit({ kind: "node", node: target.data("raw") as GraphNode });
      this.emit({ kind: "edge", edge: target.data("raw") as GraphEdge });
    });
    cy.on("select unselect", () => {
      cy.edges().removeClass("hot");
      cy.nodes(":selected").connectedEdges().addClass("hot");
      const n = cy.nodes(":selected").length;
      for (const h of this.selectionHandlers) h(n);
    });
    cy.on("dbltap", "node.Group", (evt) => {
      const id = evt.target.id();
      if (this.isCollapsed(id)) this.expand(id);
      else this.collapse(id);
    });
    cy.on("dbltap", "node.Entity", (evt) => {
      const node = evt.target.data("raw") as GraphNode;
      for (const h of this.activateHandlers) h(node);
    });

    cy.on("mouseover", "node", (evt) => {
      container.style.cursor = "pointer";
      const n = evt.target;
      const pos = n.renderedPosition();
      this.emitHover({ node: n.data("raw") as GraphNode, x: pos.x, y: pos.y - n.renderedHeight() / 2 });
    });
    cy.on("mouseout", "node", () => {
      container.style.cursor = "";
      this.emitHover(null);
    });
    cy.on("viewport drag", () => this.emitHover(null));

    // The container can be laid out after mount (grid sizing, side panels). Keep the canvas
    // size in sync, and re-fit until the user has pan/zoomed themselves.
    const markInteracted = () => (this.interacted = true);
    container.addEventListener("wheel", markInteracted, { passive: true });
    container.addEventListener("pointerdown", markInteracted);
    this.resizeObserver = new ResizeObserver(() => {
      cy.resize();
      if (!this.interacted && cy.elements().length > 0) this.fitView();
    });
    this.resizeObserver.observe(container);

    // The canvas colours come from CSS variables, so follow the theme switch and the OS setting.
    const restyle = () => this.restyle();
    this.themeObserver = new MutationObserver(restyle);
    this.themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    this.colorScheme = window.matchMedia("(prefers-color-scheme: dark)");
    this.colorScheme.addEventListener("change", restyle);
  }

  destroy(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.themeObserver?.disconnect();
    this.themeObserver = null;
    this.colorScheme = null;
    this.hoverHandlers.clear();
    this.activateHandlers.clear();
    this.cy?.destroy();
    this.cy = null;
    this.handlers.clear();
  }

  load(graph: GraphData, layout: LayoutName, focus?: string): void {
    const cy = this.must();
    this.collapsed.clear();
    this.hiddenKinds.clear();
    this.interacted = false;
    this.focus = focus ?? null;
    cy.elements().remove();
    cy.add(toElements(graph, new Set()));
    this.applyRoles();
    if (this.focus) cy.getElementById(this.focus).addClass("focus");
    this.layout(layout);
  }

  merge(graph: GraphData, layout: LayoutName): number {
    const cy = this.must();
    const before = cy.nodes();
    const existing = new Set(cy.elements().map((el) => el.id()));
    const added = cy.add(toElements(graph, existing));
    this.applyRoles();
    this.applyHidden();
    const fresh = added.nodes();
    if (fresh.length === 0) return 0;

    // Start each new node beside something it connects to, so the incremental layout grows
    // the picture outward instead of scattering the newcomers.
    const extent = cy.extent();
    fresh.forEach((n, i) => {
      const anchor = n.neighborhood("node").intersection(before).nodes().first();
      const home = anchor.nonempty()
        ? anchor.position()
        : { x: (extent.x1 + extent.x2) / 2, y: (extent.y1 + extent.y2) / 2 };
      const angle = (i / Math.max(fresh.length, 1)) * Math.PI * 2;
      n.position({ x: home.x + Math.cos(angle) * 90, y: home.y + Math.sin(angle) * 90 });
    });

    if (layout === "force") {
      cy.layout(layoutOptions("force", this.focus, before)).run();
      clearEdges(cy, before);
      separateOverlaps(cy, before);
    } else {
      this.layout(layout);
    }
    return fresh.length;
  }

  collapse(groupId: string): void {
    const node = this.must().getElementById(groupId);
    if (node.empty() || !node.isParent()) return;
    node.descendants().style("display", "none");
    node.addClass("collapsed");
    this.collapsed.add(groupId);
  }

  expand(groupId: string): void {
    const node = this.must().getElementById(groupId);
    node.descendants().style("display", "element");
    node.removeClass("collapsed");
    this.collapsed.delete(groupId);
    this.applyHidden();
  }

  isCollapsed(groupId: string): boolean {
    return this.collapsed.has(groupId);
  }

  select(id: string | null): void {
    const cy = this.must();
    cy.elements().unselect();
    const el = id ? cy.getElementById(id) : null;
    if (!el || el.empty()) return this.emit(null);
    el.select();
    const isNode = el.group() === "nodes";
    const raw: unknown = el.data("raw");
    this.emit(
      isNode ? { kind: "node", node: raw as GraphNode } : { kind: "edge", edge: raw as GraphEdge },
    );
  }

  reveal(id: string): void {
    const cy = this.must();
    const el = cy.getElementById(id);
    if (el.empty()) return;
    this.select(id);
    // Only pan when the item is off-screen or hugging an edge; re-centring something already in
    // view shoves the rest of the picture out of frame.
    const box = el.renderedBoundingBox();
    const pad = 64;
    const inside =
      box.x1 > pad && box.x2 < cy.width() - pad && box.y1 > pad && box.y2 < cy.height() - pad;
    if (!inside) {
      this.interacted = true;
      cy.animate({ center: { eles: el }, duration: 280 });
    }
  }

  zoomBy(factor: number): void {
    const cy = this.must();
    this.interacted = true;
    cy.zoom({
      level: cy.zoom() * factor,
      renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
    });
  }

  fit(): void {
    this.interacted = false;
    this.fitView();
  }

  restyle(): void {
    const cy = this.cy;
    if (!cy) return;
    cy.style(stylesheet());
    const muted = cssVar("--muted");
    cy.edges().forEach((e) => {
      e.data("color", edgeColor(e.data("raw") as GraphEdge, muted));
    });
  }

  highlight(ids: string[]): void {
    const cy = this.must();
    cy.elements().removeClass("dim hl");
    if (ids.length === 0) return;
    const keep = cy.collection();
    for (const id of ids) keep.merge(cy.getElementById(id));
    cy.elements().difference(keep.union(keep.edgesWith(keep))).addClass("dim");
    keep.nodes().addClass("hl");
  }

  layout(name: LayoutName): void {
    const cy = this.must();
    cy.resize(); // measure the container now, not at mount time
    const claims = cy
      .nodes()
      .filter((n) => n.data("entity_type") === "Claim" && n.style("display") !== "none")
      .map((n) => n.id());
    cy.layout(layoutOptions(name, this.focus, null, claims)).run();
    if (name === "force") {
      clearEdges(cy);
      separateOverlaps(cy);
    }
    this.fitView();
  }

  private selectedNodes(): cytoscape.NodeCollection {
    return this.must().nodes(":selected").filter((n) => !n.isParent()) as cytoscape.NodeCollection;
  }

  align(mode: AlignMode): void {
    const sel = this.selectedNodes();
    if (sel.length < 2) return;
    const bb = sel.boundingBox({ includeLabels: false });
    sel.positions((n) => {
      const { x, y } = n.position();
      const halfW = n.outerWidth() / 2;
      const halfH = n.outerHeight() / 2;
      switch (mode) {
        case "left":
          return { x: bb.x1 + halfW, y };
        case "right":
          return { x: bb.x2 - halfW, y };
        case "top":
          return { x, y: bb.y1 + halfH };
        case "bottom":
          return { x, y: bb.y2 - halfH };
        case "hcenter":
          return { x: (bb.x1 + bb.x2) / 2, y };
        case "vcenter":
          return { x, y: (bb.y1 + bb.y2) / 2 };
      }
    });
    this.interacted = true;
  }

  distribute(axis: "horizontal" | "vertical"): void {
    const sel = this.selectedNodes();
    if (sel.length < 3) return;
    const k = axis === "horizontal" ? "x" : "y";
    const sorted = sel.sort((a, b) => a.position(k) - b.position(k));
    const first = sorted[0].position(k);
    const step = (sorted[sorted.length - 1].position(k) - first) / (sorted.length - 1);
    sorted.forEach((n, i) => {
      n.position(k, first + step * i);
    });
    this.interacted = true;
  }

  onSelectionCount(handler: (count: number) => void): () => void {
    this.selectionHandlers.add(handler);
    return () => this.selectionHandlers.delete(handler);
  }

  kindStats(): KindStat[] {
    const stats = new Map<string, KindStat>();
    this.must().nodes().forEach((n) => {
      const key = kindOf(n);
      if (!key) return;
      const have = stats.get(key);
      if (have) {
        have.count += 1;
        return;
      }
      const raw = n.data("raw") as GraphNode;
      const v = visualKey(raw);
      stats.set(key, {
        key, tier: key.startsWith("entity:") ? 1 : 2,
        label: key === "record" ? "Source records" : VISUALS[v].label,
        icon: badgeUri(key.startsWith("entity:") ? entityKey(raw.entity_type) : v),
        count: 1, hidden: this.hiddenKinds.has(key),
      });
    });
    return [...stats.values()].sort((a, b) => a.tier - b.tier || a.label.localeCompare(b.label));
  }

  setKindHidden(key: string, hidden: boolean): void {
    if (hidden) this.hiddenKinds.add(key);
    else this.hiddenKinds.delete(key);
    this.applyHidden();
  }

  /** A person's icon shows the role they play in the claims on the canvas (strongest first);
   *  every role goes on the node so the tooltip can list them all. */
  private applyRoles(): void {
    const cy = this.must();
    cy.nodes(".Entity").filter((n) => n.data("entity_type") === "Person").forEach((n) => {
      const held = new Set(
        n.outgoers("edge.RELATED_TO").map((e) => String((e.data("raw") as GraphEdge).data.rel_type)),
      );
      const roles = ROLE_ORDER.filter((r) => held.has(r));
      const key = roles.length ? (`role_${roles[0]}` as const) : "person";
      const raw = n.data("raw") as GraphNode;
      n.data({
        color: VISUALS[key].color,
        icon: glyphUri(key),
        raw: { ...raw, data: { ...raw.data, roles } },
      });
    });
  }

  find(query: string): string[] {
    const words = fold(query).split(" ").filter(Boolean);
    if (words.length === 0) return [];
    const hits: { id: string; rank: number }[] = [];
    this.must().nodes().forEach((n) => {
      if (n.isParent() || n.style("display") === "none") return;
      const label = fold(String(n.data("label")));
      if (!words.every((w) => label.includes(w))) return;
      // Whole-label and word-start matches first, then entities before details.
      const rank = (label === words.join(" ") ? 0 : label.startsWith(words[0]) ? 1 : 2) * 2 +
        (n.data("kind") === "Entity" ? 0 : 1);
      hits.push({ id: n.id(), rank });
    });
    return hits.sort((a, b) => a.rank - b.rank || a.id.localeCompare(b.id)).map((h) => h.id);
  }

  setBoxSelect(on: boolean): void {
    this.boxSelect = on;
    this.must().userPanningEnabled(!on);
  }

  /** Hide every node of a collapsed kind (never the focus, never inside a folded group). */
  private applyHidden(): void {
    this.must().nodes().forEach((n) => {
      const key = kindOf(n);
      if (!key) return;
      const hide = this.hiddenKinds.has(key) && n.id() !== this.focus;
      if (hide) n.style("display", "none");
      else if (n.ancestors(".collapsed").empty()) n.style("display", "element");
    });
  }

  exportPng(): Promise<Blob> {
    const blob = this.must().png({ output: "blob", full: true, bg: cssVar("--bg"), scale: 2 });
    return Promise.resolve(blob);
  }

  onSelect(handler: (selection: Selection | null) => void): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  private fitView(): void {
    const cy = this.must();
    cy.fit(undefined, FIT_PADDING);
    if (cy.zoom() > MAX_FIT_ZOOM) {
      cy.zoom(MAX_FIT_ZOOM);
      cy.center();
    }
  }

  onHover(handler: (hover: HoverInfo | null) => void): () => void {
    this.hoverHandlers.add(handler);
    return () => this.hoverHandlers.delete(handler);
  }

  onActivate(handler: (node: GraphNode) => void): () => void {
    this.activateHandlers.add(handler);
    return () => this.activateHandlers.delete(handler);
  }

  private emitHover(hover: HoverInfo | null): void {
    for (const h of this.hoverHandlers) h(hover);
  }

  private emit(selection: Selection | null): void {
    for (const h of this.handlers) h(selection);
  }

  private must(): Core {
    if (!this.cy) throw new Error("GraphView is not mounted");
    return this.cy;
  }
}
