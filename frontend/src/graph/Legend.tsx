import { ATTRIBUTE_KEYS, INSURANCE_KEYS, ROLE_KEYS, VISUALS, badgeUri, type VisualKey } from "./icons";

const ENTITY_KEYS: VisualKey[] = ["person", "organization", "group", "record"];

function Item({ k }: { k: VisualKey }) {
  return (
    <li>
      <img src={badgeUri(k)} alt="" width={18} height={18} />
      {VISUALS[k].label}
    </li>
  );
}

/** Key to the icons on the canvas. Uses the same glyph file as the nodes, so they cannot drift. */
export function Legend() {
  return (
    <details className="legend">
      <summary>Legend</summary>
      <p className="legend-title">Who</p>
      <ul>
        {ENTITY_KEYS.map((k) => (
          <Item key={k} k={k} />
        ))}
      </ul>
      <p className="legend-title">Claims, policies and providers</p>
      <ul>
        {INSURANCE_KEYS.map((k) => (
          <Item key={k} k={k} />
        ))}
      </ul>
      <p className="legend-title">Roles (a person shows their strongest role)</p>
      <ul>
        {ROLE_KEYS.map((k) => (
          <Item key={k} k={k} />
        ))}
      </ul>
      <p className="legend-title">What they have in common</p>
      <ul>
        {ATTRIBUTE_KEYS.filter((k) => k !== "name").map((k) => (
          <Item key={k} k={k} />
        ))}
      </ul>
      <p className="legend-note">
        <span className="swatch swatch-hub" /> Dashed pink ring: a value shared so widely it no
        longer links people.
        <br />
        <span className="swatch swatch-risk" /> Amber or red ring: risk score 50 or 80+.
        <br />
        <span className="swatch swatch-siu" /> Red "!" on a claim: referred to, accepted by or
        decided by the special investigation unit.
        <br />
        Dotted line: a value that is no longer current.
        <br />
        <span className="swatch swatch-alias" /> Red line: probably the same person under another
        name or ID. Other arrows name the role, such as witness or passenger.
      </p>
    </details>
  );
}
