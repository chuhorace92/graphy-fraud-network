import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { Appearance, AttributeVersion, GraphEdge, GraphNode, MergeExplanation, Network } from "../api/types";
import { Badge } from "../graph/Badge";
import type { Selection } from "../graph/GraphView";
import { ATTRIBUTE_KEYS, VISUALS, visualKey, type VisualKey } from "../graph/icons";
import {
  attrLabel,
  dateRange,
  edgeSentence,
  lower,
  mergeSummary,
  plural,
  ruleLabel,
} from "../lib/friendly";
import { useCanvas } from "../state/canvasStore";
import { Icon } from "../ui/Icon";
import { Chip, ErrorNote, Skeleton, Stat, Tabs } from "../ui/kit";

export interface InspectorProps {
  selection: Selection | null;
  nodes: Map<string, GraphNode>;
  edges: Map<string, GraphEdge>;
  focus: string;
  truncated: boolean;
  expanding: string | null;
  onExpand: (n: GraphNode) => void;
  onReveal: (id: string) => void;
  onClear: () => void;
}

const holdersOf = (valueId: string, p: InspectorProps) =>
  [...p.edges.values()]
    .filter((e) => e.target === valueId)
    .map((e) => p.nodes.get(e.source))
    .filter((n): n is GraphNode => !!n);

export function Inspector(p: InspectorProps) {
  const { selection } = p;
  if (!selection) return <Overview {...p} />;
  if (selection.kind === "edge") return <EdgeView edge={selection.edge} {...p} />;
  const node = selection.node;
  switch (node.kind) {
    case "Entity":
      return <EntityView key={node.id} node={node} {...p} />;
    case "AttributeValue":
      return <ValueView key={node.id} node={node} {...p} />;
    case "SourceRecord":
      return <RecordView key={node.id} node={node} {...p} />;
    default:
      return <GenericView node={node} {...p} />;
  }
}

function Header({
  badge,
  title,
  subtitle,
  onClose,
}: {
  badge: VisualKey;
  title: string;
  subtitle?: ReactNode;
  onClose: () => void;
}) {
  return (
    <header className="insp-head">
      <Badge k={badge} size={38} />
      <div className="insp-title">
        <h2 title={title}>{title}</h2>
        {subtitle && <div className="insp-sub">{subtitle}</div>}
      </div>
      <button type="button" className="icon-btn" aria-label="Close details" title="Close" onClick={onClose}>
        <Icon name="close" />
      </button>
    </header>
  );
}

function Technical({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (entries.length === 0) return null;
  return (
    <details className="technical">
      <summary>Technical details</summary>
      <dl className="kv">
        {entries.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function NodeButton({ node, onReveal }: { node: GraphNode; onReveal: (id: string) => void }) {
  return (
    <button type="button" className="row-btn" onClick={() => onReveal(node.id)}>
      <Badge k={visualKey(node)} size={22} />
      <span className="row-main">
        <strong>{node.label}</strong>
        <span>{node.kind === "Entity" ? node.entity_type : attrLabel(String(node.data.attr_type ?? ""))}</span>
      </span>
      <Icon name="chevronRight" size={15} />
    </button>
  );
}

/* ---------------------------------------------------------------- nothing selected */

type OverviewTab = "summary" | "hits";

function Overview(p: InspectorProps) {
  const [tab, setTab] = useState<OverviewTab>("summary");
  const network = useQuery({
    queryKey: ["entity-network", p.focus],
    queryFn: () => api.entityNetwork(p.focus),
    enabled: !!p.focus, // an empty workbench has no starting point to summarise
  });
  const hitCount = network.data?.hits.length;
  if (!p.focus) {
    return (
      <div className="insp-body">
        <h2 className="insp-heading">Network summary</h2>
        {p.nodes.size > 0 ? (
          <SummaryTab {...p} />
        ) : (
          <p className="muted">Add a person, company or claim to the canvas to see its network here.</p>
        )}
      </div>
    );
  }
  return (
    <div className="insp-body">
      <h2 className="insp-heading">Network summary</h2>
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "summary", label: "Summary" },
          { value: "hits", label: hitCount === undefined ? "Analytics hits" : `Analytics hits (${hitCount})` },
        ]}
      />
      {tab === "summary" ? <SummaryTab {...p} /> : <HitsTab {...p} network={network} />}
    </div>
  );
}

/** The indicators that fired on this network: which rule, what it found, and who it involves. */
function HitsTab(p: InspectorProps & { network: UseQueryResult<Network> }) {
  const { network } = p;
  const highlighted = useCanvas((s) => s.highlighted);
  const setHighlighted = useCanvas((s) => s.setHighlighted);
  const setPreview = useCanvas((s) => s.setPreview);
  useEffect(() => () => setPreview([]), [setPreview]); // leaving the tab ends any preview
  if (network.isPending) return <Skeleton rows={4} />;
  if (network.isError) return <ErrorNote error={network.error} />;
  const n = network.data;
  if (n.hits.length === 0) {
    return (
      <div className="note">
        <Icon name="check" size={16} />
        <span>No analytics rule fired on this network.</span>
      </div>
    );
  }
  return (
    <div className="hits">
      <div className={`hits-score risk-${n.severity}`}>
        <b>{n.score}</b>
        <span>
          {n.severity} fraud indicators · {plural(n.hits.length, "hit")} across{" "}
          {plural(n.size, "entity", "entities")}
        </span>
      </div>
      <ul>
        {n.hits.map((h) => {
          const on = h.entities.length > 0 && h.entities.every((id) => highlighted.includes(id));
          return (
            <li
              key={`${h.rule_id}-${h.detail}`}
              className={`ahit ahit-${h.severity}`}
              onMouseEnter={() => setPreview(h.entities)}
              onMouseLeave={() => setPreview([])}
              onFocus={() => setPreview(h.entities)}
              onBlur={() => setPreview([])}
            >
              <div className="ahit-head">
                <span className={`risk risk-${h.severity}`}>{h.severity}</span>
                <span className="ahit-pts">+{h.points}</span>
              </div>
              <strong>{h.detail}</strong>
              <span className="muted small">{h.title}</span>
              <button
                type="button"
                className="link-btn"
                onClick={() => setHighlighted(on ? [] : h.entities)}
              >
                {on ? "Clear highlight" : `Show ${plural(h.entities.length, "entity", "entities")} on graph`}
              </button>
            </li>
          );
        })}
      </ul>
      <p className="muted small">
        Rules are listed on the Analytics page. Each hit adds points by severity, up to 100.
      </p>
    </div>
  );
}

const GROUPS = [["people", "People"], ["companies", "Companies"], ["objects", "Objects"]] as const;

function SummaryTab(p: InspectorProps) {
  const { nodes } = p;
  const [group, setGroup] = useState<(typeof GROUPS)[number][0]>("people");
  const summary = useMemo(() => {
    const all = [...nodes.values()];
    const entities = all.filter((n) => n.kind === "Entity");
    const values = all.filter((n) => n.kind === "AttributeValue");
    const holders = (n: GraphNode) => (typeof n.data.holders === "number" ? n.data.holders : 0);
    const byName = [...entities].sort((a, b) =>
      a.id === p.focus ? -1 : b.id === p.focus ? 1 : a.label.localeCompare(b.label),
    );
    const OBJECTS = ["Claim", "Policy", "Property", "Vehicle"];
    const kind = (n: GraphNode) =>
      n.entity_type === "Person" ? "people" : OBJECTS.includes(n.entity_type ?? "") ? "objects" : "companies";
    return {
      // Providers (legal, medical, body shops) are businesses, so they sit with the companies.
      people: byName.filter((n) => kind(n) === "people"),
      companies: byName.filter((n) => kind(n) === "companies"),
      objects: byName.filter((n) => kind(n) === "objects"),
      shared: values.filter((n) => holders(n) > 1 && n.status !== "hub"),
      hubs: values.filter((n) => n.status === "hub").length,
    };
  }, [nodes, p.focus]);

  const top = [...summary.shared]
    .sort((a, b) => Number(b.data.holders) - Number(a.data.holders))
    .slice(0, 6);

  return (
    <>
      <div className="stats">
        <Stat value={summary.people.length} label={summary.people.length === 1 ? "person" : "people"} />
        <Stat
          value={summary.companies.length}
          label={summary.companies.length === 1 ? "company" : "companies"}
        />
        <Stat value={summary.objects.length} label={summary.objects.length === 1 ? "object" : "objects"} />
        <Stat value={summary.shared.length} label="shared details" />
        {summary.hubs > 0 && <Stat value={summary.hubs} label="widely shared" />}
      </div>
      {p.truncated && (
        <div className="note warn">
          <Icon name="alert" size={16} />
          <span>This network is larger than what is shown. Lower the reach, or expand one person at a time.</span>
        </div>
      )}

      <Tabs
        value={group}
        onChange={setGroup}
        tabs={GROUPS.map(([value, label]) => ({ value, label: `${label} (${summary[value].length})` }))}
      />
      {group === "objects" && (
        <p className="muted small">Claims, policies, properties and vehicles.</p>
      )}
      {summary[group].length === 0 ? (
        <p className="muted small">None in this network.</p>
      ) : (
        <div className="rows scroll">
          {summary[group].map((n) => (
            <NodeButton key={n.id} node={n} onReveal={p.onReveal} />
          ))}
        </div>
      )}

      {top.length > 0 && (
        <section>
          <h3>What connects them</h3>
          <p className="muted small">The most widely shared details here. Click one to see who holds it.</p>
          <div className="rows">
            {top.map((n) => (
              <button key={n.id} type="button" className="row-btn" onClick={() => p.onReveal(n.id)}>
                <Badge k={visualKey(n)} size={22} />
                <span className="row-main">
                  <strong>{n.label}</strong>
                  <span>
                    {attrLabel(String(n.data.attr_type))} · shared by {Number(n.data.holders)}
                  </span>
                </span>
                <Icon name="chevronRight" size={15} />
              </button>
            ))}
          </div>
        </section>
      )}


      <div className="note">
        <Icon name="info" size={16} />
        <span>
          Click anything to see why it is there. Double-click a person to reveal who else they are
          connected to.
        </span>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- an entity */

type EntityTab = "details" | "history" | "evidence";

function groupByType(rows: AttributeVersion[]): [string, AttributeVersion[]][] {
  const by = new Map<string, AttributeVersion[]>();
  for (const r of rows) by.set(r.attr_type, [...(by.get(r.attr_type) ?? []), r]);
  const order = (t: string) => {
    const i = ATTRIBUTE_KEYS.indexOf(t as VisualKey);
    return i === -1 ? 99 : i;
  };
  return [...by.entries()].sort((a, b) => order(a[0]) - order(b[0]));
}

const CLAIM_FIELDS = ["loss_type", "loss_date", "fnol_date", "claim_status", "claim_amount",
  "siu_referred", "siu_accepted", "siu_outcome",
  "loss_description"];

/** A claim at a glance: type tags, dates, status, amount and what happened. */
function ClaimSummary({ rows }: { rows: AttributeVersion[] }) {
  const by = (t: string) => rows.filter((r) => r.attr_type === t);
  const one = (t: string) => by(t)[0]?.display;
  const tags = by("loss_type");
  const lag = (() => {
    const [a, b] = [by("loss_date")[0]?.display, by("fnol_date")[0]?.display];
    if (!a || !b) return null;
    return Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);
  })();
  return (
    <div className="claim-summary">
      <div className="claim-tags">
        {tags.map((t) => (
          <span key={t.value_id} className={`tag ${t.display === "Bodily Injury" ? "tag-bi" : "tag-pd"}`}>
            {t.display}
          </span>
        ))}
        {one("claim_status") && <Chip>{one("claim_status")}</Chip>}
      </div>
      {one("loss_description") && <p className="claim-what">{one("loss_description")}</p>}
      <dl>
        <dt>Date of loss</dt>
        <dd>{one("loss_date") ?? "Unknown"}</dd>
        <dt>First notice of loss</dt>
        <dd>
          {one("fnol_date") ?? "Unknown"}
          {lag !== null && <span className="muted"> · {lag === 0 ? "same day" : `${lag} days after`}</span>}
        </dd>
        <dt>Claimed amount</dt>
        <dd>{one("claim_amount") ?? "Unknown"}</dd>
        <dt>Referred to SIU</dt>
        <dd>{one("siu_referred") ?? "Unknown"}</dd>
        <dt>Accepted to SIU</dt>
        <dd>{one("siu_accepted") ?? "Unknown"}</dd>
        <dt>SIU outcome</dt>
        <dd>{one("siu_outcome") ?? "Unknown"}</dd>
      </dl>
    </div>
  );
}

/** One row per time this entity was filed: the name used, the claim, the role and what else
 *  came with it. Records are the same entity re-entered by different people on different claims. */
function Appearances({ rows, why, type }: { rows: Appearance[]; why: MergeExplanation[]; type: string }) {
  const basis = new Map(why.map((w) => [w.record_id, w]));
  const claims = new Set(rows.flatMap((r) => r.links.map((l) => l.claim_id)));
  return (
    <>
      <p className="muted small">
        Filed {plural(rows.length, "time")}
        {claims.size > 0 && <> across {plural(claims.size, "claim")}</>}.
      </p>
      <table className="appearances">
        <thead>
          <tr>
            <th>Name</th>
            <th>Claim</th>
            <th>Role</th>
            <th>Attributes</th>
          </tr>
        </thead>
        {rows.map((r) => {
          const w = basis.get(r.record_id);
          const links = r.links.length ? r.links : [null];
          return (
            <tbody key={r.record_id}>
              {links.map((l, i) => (
                <tr key={l?.claim_id ?? "none"}>
                  {i === 0 && (
                    <td rowSpan={links.length}>
                      <strong>{r.name ?? "Unnamed"}</strong>
                      <div className="muted mono">{r.record_id}</div>
                      <div className="muted">
                        {[r.source_system, w?.rules_fired.filter((x) => x !== "singleton").map(ruleLabel).join(", ")]
                          .filter(Boolean)
                          .join(" · ")}
                        {w?.method === "manual" && " (manual)"}
                      </div>
                    </td>
                  )}
                  <td>{l?.claim ?? "–"}</td>
                  <td>{l ? lower(l.role.replace(/_/g, " ")) : "–"}</td>
                  {i === 0 && (
                    <td rowSpan={links.length}>
                      {r.attributes.length === 0 && "–"}
                      {r.attributes.map((a) => (
                        <div key={`${a.attr_type}-${a.display}`}>
                          <span className="muted">{attrLabel(a.attr_type, type)}</span> {a.display}
                        </div>
                      ))}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          );
        })}
      </table>
    </>
  );
}

function EntityView(p: InspectorProps & { node: GraphNode }) {
  const { node } = p;
  const [tab, setTab] = useState<EntityTab>("details");
  const detail = useQuery({ queryKey: ["entity", node.id], queryFn: () => api.entity(node.id) });
  const attrs = useQuery({ queryKey: ["attributes", node.id], queryFn: () => api.attributes(node.id) });
  const why = useQuery({ queryKey: ["explain", node.id], queryFn: () => api.explain(node.id) });
  const seen = useQuery({ queryKey: ["appearances", node.id], queryFn: () => api.appearances(node.id) });
  const busy = p.expanding === node.id;
  const type = node.entity_type ?? "Person";

  return (
    <div className="insp">
      <Header
        badge={visualKey(node)}
        title={detail.data?.canonical_name ?? node.label}
        onClose={p.onClear}
        subtitle={
          <>
            <Chip>{type}</Chip>
            {detail.data && <Chip>{plural(detail.data.record_count, "source record")}</Chip>}
            {node.id === p.focus && <Chip tone="accent">Starting point</Chip>}
          </>
        }
      />
      <div className="insp-actions">
        <button type="button" className="btn primary" disabled={busy} onClick={() => p.onExpand(node)}>
          <Icon name="expand" size={16} />
          {busy ? "Loading…" : "Show connections"}
        </button>
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "details", label: "Details" },
          { value: "history", label: "History" },
          { value: "evidence", label: "Evidence" },
        ]}
      />

      <div className="insp-body">
        {attrs.isPending && <Skeleton rows={5} />}
        {attrs.isError && <ErrorNote error={attrs.error} />}

        {tab === "details" && attrs.data && type === "Claim" && <ClaimSummary rows={attrs.data} />}

        {tab === "details" && attrs.data && (
          <div className="rows">
            {groupByType(attrs.data)
              .filter(([t]) => type !== "Claim" || !CLAIM_FIELDS.includes(t))
              .map(([t, versions]) => {
              const current = versions.filter((v) => v.is_current);
              const shown = current.length ? current : versions.slice(0, 1);
              return shown.map((v) => (
                <div key={`${t}-${v.value_id}`} className="detail-row">
                  <Badge k={(t in VISUALS ? t : "attribute") as VisualKey} size={24} />
                  <span className="row-main">
                    <span>{attrLabel(t, type)}</span>
                    <strong>{v.display}</strong>
                  </span>
                  {v.is_hub ? (
                    <Chip tone="warn" title="Shared by so many that it no longer links people">
                      widely shared
                    </Chip>
                  ) : (
                    v.shared_with > 0 &&
                    (p.nodes.has(v.value_id) ? (
                      <button type="button" className="chip chip-accent chip-btn" onClick={() => p.onReveal(v.value_id)}>
                        shared with {v.shared_with}
                      </button>
                    ) : (
                      <Chip tone="accent">shared with {v.shared_with}</Chip>
                    ))
                  )}
                </div>
              ));
            })}
          </div>
        )}

        {tab === "history" && attrs.data && (
          <div className="history">
            <p className="muted small">Every value seen for this {lower(type)}, newest first, with where it came from.</p>
            {groupByType(attrs.data).map(([t, versions]) => (
              <section key={t}>
                <h3>
                  {attrLabel(t, type)}{" "}
                  <span className="muted">
                    {versions.length === 1 ? "· no changes" : `· ${versions.length} values`}
                  </span>
                </h3>
                <ol className="timeline">
                  {versions.map((v) => (
                    <li key={`${v.value_id}-${v.record_id}`} className={v.is_current ? "now" : ""}>
                      <strong>{v.display}</strong>
                      <span>
                        {v.is_current ? "Current · " : ""}
                        {dateRange(v.first_seen, v.last_seen)}
                        {v.source_system ? ` · ${v.source_system}` : ""}
                      </span>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
        )}

        {tab === "evidence" && (
          <div>
            {why.isPending && <Skeleton rows={3} />}
            {why.isError && <ErrorNote error={why.error} />}
            {why.data && (
              <>
                <h3>Why these records are one {lower(type)}</h3>
                <p>{mergeSummary(why.data, type)}</p>
                {seen.isError && <ErrorNote error={seen.error} />}
                {seen.data && <Appearances rows={seen.data} why={why.data} type={type} />}
                <div className="note">
                  <Icon name="info" size={16} />
                  <span>
                    Source records are never changed. If a merge is wrong, a steward can split it and the
                    decision is kept on every future run.
                  </span>
                </div>
                {detail.data?.rule_set_version && (
                  <p className="muted small">Rules applied: {detail.data.rule_set_version}</p>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- a shared detail */

function ValueView(p: InspectorProps & { node: GraphNode }) {
  const { node } = p;
  const type = String(node.data.attr_type ?? "attribute");
  const holders = holdersOf(node.id, p);
  const masked = node.label.startsWith("•");
  const degree = typeof node.data.degree === "number" ? node.data.degree : null;
  return (
    <div className="insp">
      <Header
        badge={visualKey(node)}
        title={node.label}
        onClose={p.onClear}
        subtitle={
          <>
            <Chip>{attrLabel(type)}</Chip>
            {node.status === "hub" && <Chip tone="warn">widely shared</Chip>}
          </>
        }
      />
      <div className="insp-body">
        <p>
          {node.status === "hub" ? (
            <>
              This {lower(attrLabel(type))} is held by {degree ? plural(degree, "entity", "entities") : "very many entities"}
              , too many to treat as a real link. It is shown for reference and does not connect them.
            </>
          ) : (
            <>
              {plural(holders.length, "person or company", "people and companies")} on this graph{" "}
              {holders.length === 1 ? "has" : "have"} this {lower(attrLabel(type))}
              {degree && degree > holders.length ? ` (${degree} in total)` : ""}.
            </>
          )}
        </p>
        {masked && (
          <div className="note">
            <Icon name="info" size={16} />
            <span>Sensitive value. It is stored only as a protected hash and shown masked.</span>
          </div>
        )}
        <h3>Held by</h3>
        <div className="rows">
          {holders.map((h) => (
            <NodeButton key={h.id} node={h} onReveal={p.onReveal} />
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- a link */

function EdgeView(p: InspectorProps & { edge: GraphEdge }) {
  const { edge } = p;
  const a = p.nodes.get(edge.source);
  const b = p.nodes.get(edge.target);
  const dated = edge.type === "HAS_ATTRIBUTE";
  return (
    <div className="insp">
      <header className="insp-head">
        <span className="badge-line">
          <Icon name="network" size={20} />
        </span>
        <div className="insp-title">
          <h2>Why these are linked</h2>
        </div>
        <button type="button" className="icon-btn" aria-label="Close details" onClick={p.onClear}>
          <Icon name="close" />
        </button>
      </header>
      <div className="insp-body">
        <p className="lead-sentence">{edgeSentence(edge, p.nodes)}</p>
        {dated && (
          <p className="muted">
            {edge.data.is_current === false ? "No longer current. " : "Current. "}
            Seen {dateRange(String(edge.data.first_seen ?? ""), String(edge.data.last_seen ?? ""))}.
          </p>
        )}
        <div className="rows">
          {[a, b].map((n) => n && <NodeButton key={n.id} node={n} onReveal={p.onReveal} />)}
        </div>
        <Technical data={edge.data} />
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- a source record */

function RecordView(p: InspectorProps & { node: GraphNode }) {
  const { node } = p;
  const rules = Array.isArray(node.data.rules_fired) ? (node.data.rules_fired as string[]) : [];
  return (
    <div className="insp">
      <Header
        badge="record"
        title={node.label}
        onClose={p.onClear}
        subtitle={<Chip>{String(node.data.source_system ?? "source")}</Chip>}
      />
      <div className="insp-body">
        <p>
          A row exactly as it arrived from {String(node.data.source_system ?? "its source system")}. It
          is kept unchanged so any merge can be undone.
        </p>
        {rules.length > 0 && (
          <p className="muted">
            Combined with others because of{" "}
            {rules.filter((r) => r !== "singleton").map(ruleLabel).join(", ") || "nothing: it stands alone"}.
          </p>
        )}
        <Technical data={node.data} />
      </div>
    </div>
  );
}

function GenericView(p: InspectorProps & { node: GraphNode }) {
  return (
    <div className="insp">
      <Header badge={visualKey(p.node)} title={p.node.label} onClose={p.onClear} />
      <div className="insp-body">
        <Technical data={p.node.data} />
      </div>
    </div>
  );
}
