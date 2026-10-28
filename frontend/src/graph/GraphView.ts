import type { GraphData, GraphEdge, GraphNode } from "../api/types";

/**
 * The only way the UI touches the graph renderer (TRD 6, "Renderer choice").
 *
 * CytoscapeGraphView is the open-source implementation. A yFiles implementation of this same
 * interface can replace it after the Phase 1 renderer spike (TRD decision D1) without
 * changing any page code.
 */
export type LayoutName = "force" | "hierarchical" | "concentric";

/** Alignment of the selected nodes to their common bounding box. "hcenter" puts them in one
 *  column, "vcenter" in one row (the PowerPoint meaning of Align Center / Align Middle). */
export type AlignMode = "left" | "right" | "top" | "bottom" | "hcenter" | "vcenter";

/** One row of the collapse/expand menu. Tier 1 is the detail clutter (attribute values and
 *  source records); tier 2 is whole kinds of entity (claims, providers, people...). */
export interface KindStat {
  key: string;
  tier: 1 | 2;
  label: string;
  icon: string;
  count: number;
  hidden: boolean;
}

export type Selection = { kind: "node"; node: GraphNode } | { kind: "edge"; edge: GraphEdge };

export interface HoverInfo {
  node: GraphNode;
  /** Position inside the canvas container, in pixels, of the top of the node. */
  x: number;
  y: number;
}

export interface GraphView {
  mount(container: HTMLElement): void;
  destroy(): void;
  /** Replace everything on the canvas. `focus` is the entity the view is centred on. */
  load(graph: GraphData, layout: LayoutName, focus?: string): void;
  /** Add nodes and edges not already present (expansion); existing nodes keep their place.
   *  Returns how many nodes were new. */
  merge(graph: GraphData, layout: LayoutName): number;
  collapse(groupId: string): void;
  expand(groupId: string): void;
  isCollapsed(groupId: string): boolean;
  /** Select an item (or clear the selection) and notify `onSelect` listeners. */
  select(id: string | null): void;
  /** Select an item and pan to it. */
  reveal(id: string): void;
  zoomBy(factor: number): void;
  /** Fit everything in view and resume auto-fitting on resize. */
  fit(): void;
  /** Re-read theme colours (light/dark switch). */
  restyle(): void;
  /** Emphasize these node ids and dim everything else; an empty list clears it. */
  highlight(ids: string[]): void;
  layout(name: LayoutName): void;
  /** Line up the selected nodes. Needs two or more. */
  align(mode: AlignMode): void;
  /** Space the selected nodes evenly between the outermost two. Needs three or more. */
  distribute(axis: "horizontal" | "vertical"): void;
  /** Drag on empty canvas draws a selection box (true) or pans the view (false). Shift-drag
   *  always draws the box. */
  setBoxSelect(on: boolean): void;
  /** Ids of the visible nodes whose label contains every word of `query`, best match first. */
  find(query: string): string[];
  /** How many nodes are selected, for enabling the toolkit. */
  onSelectionCount(handler: (count: number) => void): () => void;
  /** What is on the canvas, by kind, with whether each kind is collapsed. */
  kindStats(): KindStat[];
  /** Collapse (hide) or expand (show) every node of a kind. The focus node never hides. */
  setKindHidden(key: string, hidden: boolean): void;
  exportPng(): Promise<Blob>;
  onSelect(handler: (selection: Selection | null) => void): () => void;
  onHover(handler: (hover: HoverInfo | null) => void): () => void;
  /** Double-click on an entity: the caller decides what that means (expand connections). */
  onActivate(handler: (node: GraphNode) => void): () => void;
}
