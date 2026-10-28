import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "../../api/client";
import type { CaseMember } from "../../api/types";
import { Badge } from "../../graph/Badge";
import { entityKey, VISUALS, type VisualKey } from "../../graph/icons";
import { attrLabel, formatDate, plural } from "../../lib/friendly";
import { Icon } from "../../ui/Icon";
import { Chip, ErrorNote, Skeleton, Stat } from "../../ui/kit";
import type { TabProps } from "./shared";

/** The things a claim is made of; the people and businesses are what this tab is about. */
const OBJECTS = new Set(["Claim", "Policy", "Vehicle", "Property"]);

const TYPE_LABEL: Record<string, string> = {
  Person: "Person",
  Organization: "Company",
  LegalRep: "Attorney",
  MedicalProvider: "Medical provider",
  BodyShop: "Body shop",
};

const role = (r: string) => r.replace(/_/g, " ");

/** The people, companies and providers in the case: a list on the left, the selected one's
 *  record on the right. */
export function PartiesTab({ detail }: TabProps) {
  const parties = useMemo(
    () =>
      detail.members
        .filter((m) => !OBJECTS.has(m.entity_type))
        .sort((a, b) => b.claims - a.claims || a.label.localeCompare(b.label)),
    [detail.members],
  );
  const [picked, setPicked] = useState<string | null>(null);
  const [type, setType] = useState("");
  const [text, setText] = useState("");
  const selected = parties.find((p) => p.entity_id === picked) ?? parties[0];
  const types = [...new Set(parties.map((p) => p.entity_type))];
  const q = text.trim().toLowerCase();
  const shown = parties.filter((p) => (!type || p.entity_type === type) && (!q || p.label.toLowerCase().includes(q)));
  return (
    <div className="pv-split">
      <section className="pv-list-wrap" aria-label="Parties in this case">
        <div className="pv-list-head">
          <label className="search-box">
            <Icon name="search" size={15} />
            <input
              type="search"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Filter by name…"
              aria-label="Filter parties"
            />
          </label>
          <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Filter by type">
            <option value="">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABEL[t] ?? t}
              </option>
            ))}
          </select>
          <span className="muted small">
            {q || type ? `${shown.length} of ${parties.length}` : plural(parties.length, "party", "parties")} · most claims first
          </span>
        </div>
        <ul className="pv-list">
          {shown.map((m) => (
            <li key={m.entity_id}>
              <PartyRow m={m} active={m.entity_id === selected?.entity_id} onSelect={() => setPicked(m.entity_id)} />
            </li>
          ))}
          {shown.length === 0 && <li className="muted small pv-none">Nobody matches.</li>}
        </ul>
      </section>
      <section className="pv-detail" aria-label="Record">
        {selected && (
          <>
            <header className="pv-head">
              <Badge k={entityKey(selected.entity_type)} size={40} />
              <div>
                <h3>{selected.label}</h3>
                <Chip>{TYPE_LABEL[selected.entity_type] ?? selected.entity_type}</Chip>
              </div>
            </header>
            <PartyRecord key={selected.entity_id} m={selected} />
          </>
        )}
      </section>
    </div>
  );
}

function PartyRow({ m, active, onSelect }: { m: CaseMember; active: boolean; onSelect: () => void }) {
  return (
    <button type="button" className={`pv-row${active ? " active" : ""}`} aria-current={active} onClick={onSelect}>
      <Badge k={entityKey(m.entity_type)} size={32} />
      <span className="pt-main">
        <strong>{m.label}</strong>
        <span className="muted small">
          {TYPE_LABEL[m.entity_type] ?? m.entity_type} · on {plural(m.claims, "claim")}
          {m.roles.length > 0 && ` · ${m.roles.map(role).join(", ")}`}
        </span>
      </span>
    </button>
  );
}

/** One party's record: what they are on, and what they hold that others hold too. */
function PartyRecord({ m }: { m: CaseMember }) {
  const appearances = useQuery({ queryKey: ["appearances", m.entity_id], queryFn: () => api.appearances(m.entity_id) });
  const attrs = useQuery({ queryKey: ["attributes", m.entity_id], queryFn: () => api.attributes(m.entity_id) });
  if (appearances.isPending || attrs.isPending) return <div className="pc-body"><Skeleton rows={5} /></div>;
  if (appearances.isError || attrs.isError) {
    return <div className="pc-body"><ErrorNote error={appearances.error ?? attrs.error} /></div>;
  }
  const links = new Map<string, { claim: string; roles: Set<string> }>();
  for (const a of appearances.data) {
    for (const l of a.links) {
      const entry = links.get(l.claim_id) ?? { claim: l.claim, roles: new Set<string>() };
      entry.roles.add(l.role);
      links.set(l.claim_id, entry);
    }
  }
  // The values held now, once each; a name or date of birth describes the party, the rest can be shared.
  const current = new Map<string, (typeof attrs.data)[number]>();
  for (const v of attrs.data) if (v.is_current && !current.has(v.value_id)) current.set(v.value_id, v);
  const held = [...current.values()].sort((a, b) => a.attr_type.localeCompare(b.attr_type));
  const sharedWithOthers = held.filter((v) => v.shared_with > 0 && !v.is_hub).length;
  return (
    <div className="pc-body">
      <div className="stats">
        <Stat value={links.size} label="claims" />
        <Stat value={appearances.data.length} label="source records" />
        <Stat value={sharedWithOthers} label="details shared with others" />
      </div>
      <div className="pc-columns">
        <section>
          <h4>Details</h4>
          {held.length === 0 && <p className="muted small">Nothing on file.</p>}
          <div className="rows">
            {held.map((v) => (
              <div key={v.value_id} className="detail-row">
                <Badge k={(v.attr_type in VISUALS ? v.attr_type : "record") as VisualKey} size={24} />
                <span className="row-main">
                  <span>{attrLabel(v.attr_type, m.entity_type)}</span>
                  <strong>{v.display}</strong>
                </span>
                {v.is_hub ? (
                  <Chip tone="warn" title="Shared by so many that it no longer links anyone">widely shared</Chip>
                ) : (
                  v.shared_with > 0 && <Chip tone="warn">shared with {v.shared_with}</Chip>
                )}
              </div>
            ))}
          </div>
        </section>
        <section>
          <h4>On claims</h4>
          {links.size === 0 ? (
            <p className="muted small">Not on any claim.</p>
          ) : (
            <table className="data compact">
              <thead>
                <tr>
                  <th>Claim</th>
                  <th>As</th>
                </tr>
              </thead>
              <tbody>
                {[...links.entries()].map(([id, l]) => (
                  <tr key={id}>
                    <td>{l.claim}</td>
                    <td>{[...l.roles].map(role).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {appearances.data.some((a) => a.source_system) && (
            <p className="muted small">
              Filed by {[...new Set(appearances.data.map((a) => a.source_system).filter(Boolean))].join(" and ")}
              {attrs.data.length > 0 && `; first seen ${formatDate(attrs.data.map((v) => v.first_seen).filter(Boolean).sort()[0])}`}.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
