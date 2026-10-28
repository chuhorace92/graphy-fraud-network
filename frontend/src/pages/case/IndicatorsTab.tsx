import type { Hit, HitMatch } from "../../api/types";
import { attrLabel, plural } from "../../lib/friendly";
import { Icon } from "../../ui/Icon";
import type { TabProps } from "./shared";

/** Why each kind of indicator counts, in a sentence. */
const WHY: Record<string, string> = {
  "shared-attribute-two-parties":
    "Different people or companies using the same phone, address, account or device may be one operation under several names.",
  "medical-and-legal-on-three-claims":
    "The same clinic and attorney on claim after claim is a classic sign of a referral or staged-accident scheme.",
  "legal-and-bodyshop-on-three-claims":
    "The same attorney and body shop on claim after claim points to a steered or staged repair and injury pattern.",
  "same-group-shifting-roles-auto-claims":
    "The same people turning up as driver, passenger and claimant on different accidents suggests staged collisions.",
  "repeat-participants": "Ordinary people are rarely on many claims; the same names keep recurring in rings.",
  "probable-aliases": "One person under another name or ID can hide how many claims they are really on.",
  "claims-bunched-in-time": "A burst of claims in a short window is unusual for one group of people.",
  "claims-soon-after-policy-start": "Losses soon after a policy begins are a known warning sign.",
};

/** The indicators that fired on this network: the rule, the data it matched, and its weight. */
export function IndicatorsTab({ detail }: TabProps) {
  const { hits } = detail.network;
  const names = new Map(detail.members.map((m) => [m.entity_id, m.label]));
  if (hits.length === 0) {
    return (
      <div className="note">
        <Icon name="check" size={16} />
        <span>No analytics rule fired on this network.</span>
      </div>
    );
  }
  const total = hits.reduce((sum, h) => sum + h.points, 0);
  return (
    <>
      <p className="muted score-sum">
        Fraud score <strong>{detail.summary.score}</strong>: the points of the indicators below added up
        {total > 100 ? ` (${total}, capped at 100)` : ` (${hits.map((h) => h.points).join(" + ")})`}.
      </p>
      <ul className="indicators">
        {hits.map((h) => (
          <li key={`${h.rule_id}-${h.detail}`} className={`ahit ahit-${h.severity}`}>
            <div className="ahit-head">
              <span className={`risk risk-${h.severity}`}>{h.severity}</span>
              <strong>{h.title}</strong>
              <span className="ahit-pts">+{h.points} points</span>
            </div>
            <p className="hit-found">{h.detail}</p>
            <dl className="hit-explain">
              {h.condition && (
                <>
                  <dt>Rule</dt>
                  <dd>{h.condition}.</dd>
                </>
              )}
              {WHY[h.rule_id] && (
                <>
                  <dt>Why it counts</dt>
                  <dd>{WHY[h.rule_id]}</dd>
                </>
              )}
            </dl>
            {h.matches.length > 0 ? <Matched hit={h} names={names} /> : <Involved hit={h} names={names} />}
          </li>
        ))}
      </ul>
    </>
  );
}

/** What one match is, in words. */
function describeMatch(m: HitMatch): string {
  switch (m.kind) {
    case "value":
      return `${m.attr_type ? attrLabel(m.attr_type) : "Detail"}${m.value ? ` ${m.value}` : ""}`;
    case "claims":
      return m.note || `Together on ${plural(m.claims.length, "claim")}`;
    case "group":
      return `A group on ${plural(m.claims.length, "shared claim")}`;
    case "person":
      return `On ${plural(m.claims.length, "claim")}`;
    case "alias":
      return "Probable alias: one person under two names or IDs";
  }
}

/** The records the indicator matched: what was matched, who, and which claims. */
function Matched({ hit, names }: { hit: Hit; names: Map<string, string> }) {
  return (
    <div className="hit-data">
      <h4>Matched data</h4>
      <table className="data compact">
        <thead>
          <tr>
            <th>Matched</th>
            <th>Who</th>
            <th>Claims</th>
          </tr>
        </thead>
        <tbody>
          {hit.matches.map((m, i) => (
            <tr key={`${m.kind}-${m.value_id ?? ""}-${m.entities.join(",")}-${i}`}>
              <td className={m.kind === "value" ? "mono" : ""}>{describeMatch(m)}</td>
              <td>
                <Chips ids={m.entities} names={names} />
                {m.kind === "value" && <span className="muted small"> · {plural(m.entities.length, "party", "parties")}</span>}
              </td>
              <td>{m.claims.length ? <Chips ids={m.claims} names={names} /> : <span className="muted">–</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Involved({ hit, names }: { hit: Hit; names: Map<string, string> }) {
  return (
    <div className="hit-data">
      <h4>Involved</h4>
      <Chips ids={hit.entities} names={names} />
    </div>
  );
}

function Chips({ ids, names }: { ids: string[]; names: Map<string, string> }) {
  return (
    <span className="holders">
      {ids.map((id) => (
        <span key={id} className="holder">
          {names.get(id) ?? id}
        </span>
      ))}
    </span>
  );
}
