import { type ReactNode, useEffect, useRef, useState } from "react";

import type { GraphData, SearchHit } from "../api/types";
import { attrLabel, plural } from "../lib/friendly";
import { useCanvas } from "../state/canvasStore";
import { Icon } from "../ui/Icon";
import { CanvasToolkit } from "./CanvasToolkit";
import { CytoscapeGraphView } from "./CytoscapeGraphView";
import type { GraphView, HoverInfo, LayoutName } from "./GraphView";
import { Legend } from "./Legend";

interface Props {
  base: GraphData | undefined;
  expansions: GraphData[];
  layout: LayoutName;
  /** The entity the view is centred on. */
  focus?: string;
  onReady?: (view: GraphView) => void;
  /** Search-and-add from the toolkit; omit to hide the panel. */
  onAddEntity?: (hit: SearchHit) => void;
  /** Label of the entity a newly added one is linked back to. */
  anchorLabel?: string;
  /** Overlays drawn on top of the canvas (messages, empty states). */
  children?: ReactNode;
}

function Tooltip({ hover }: { hover: HoverInfo }) {
  const { node } = hover;
  const type = typeof node.data.attr_type === "string" ? node.data.attr_type : null;
  const holders = typeof node.data.holders === "number" ? node.data.holders : null;
  const roles = Array.isArray(node.data.roles) ? (node.data.roles as string[]) : [];
  const subtitle =
    node.kind === "Entity"
      ? roles.length > 0
        ? `${node.entity_type} · ${roles.join(", ")}`
        : node.entity_type
      : node.kind === "AttributeValue"
        ? `${type ? attrLabel(type) : "Detail"}${holders ? ` · held by ${plural(holders, "entity", "entities")}` : ""}`
        : node.kind === "SourceRecord"
          ? "Source record"
          : node.kind;
  return (
    <div className="tooltip" style={{ left: hover.x, top: hover.y }} role="tooltip">
      <strong>{node.label}</strong>
      <span>{subtitle}</span>
      {node.kind === "Entity" && <em>Double-click to show connections</em>}
    </div>
  );
}

/** Owns one GraphView. `base` replaces the canvas; each new expansion is merged in place. */
export function GraphCanvas({
  base, expansions, layout, focus, onReady, onAddEntity, anchorLabel, children,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const view = useRef<GraphView | null>(null);
  const merged = useRef(0);
  const setSelection = useCanvas((s) => s.setSelection);
  const highlighted = useCanvas((s) => s.highlighted);
  const preview = useCanvas((s) => s.preview);
  const found = useCanvas((s) => s.found);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [ready, setReady] = useState<GraphView | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const v = new CytoscapeGraphView();
    v.mount(container.current);
    const offs = [v.onSelect(setSelection), v.onHover(setHover)];
    view.current = v;
    setReady(v);
    onReady?.(v);
    return () => {
      offs.forEach((off) => off());
      v.destroy();
      view.current = null;
      setReady(null);
    };
  }, []);

  useEffect(() => {
    if (!view.current || !base) return;
    view.current.load(base, layout, focus);
    merged.current = 0;
  }, [base]);

  useEffect(() => {
    if (!view.current) return;
    for (const g of expansions.slice(merged.current)) view.current.merge(g, layout);
    merged.current = expansions.length;
  }, [expansions]);

  useEffect(() => {
    if (base) view.current?.layout(layout);
  }, [layout]);

  useEffect(() => {
    view.current?.highlight(preview.length > 0 ? preview : found.length > 0 ? found : highlighted);
  }, [highlighted, preview, found]);

  return (
    <div className="canvas-wrap">
      <div ref={container} className="canvas" role="img" aria-label="Network graph" />
      {hover && <Tooltip hover={hover} />}
      <div className="zoom" role="group" aria-label="Zoom">
        <button type="button" title="Zoom in" aria-label="Zoom in" onClick={() => view.current?.zoomBy(1.3)}>
          <Icon name="plus" />
        </button>
        <button type="button" title="Zoom out" aria-label="Zoom out" onClick={() => view.current?.zoomBy(1 / 1.3)}>
          <Icon name="minus" />
        </button>
        <button type="button" title="Fit to screen" aria-label="Fit to screen" onClick={() => view.current?.fit()}>
          <Icon name="fit" />
        </button>
      </div>
      <CanvasToolkit
        view={ready}
        onAddEntity={onAddEntity}
        anchorLabel={anchorLabel}
        version={(base?.nodes.length ?? 0) + expansions.length}
      />
      <Legend />
      {children}
    </div>
  );
}
