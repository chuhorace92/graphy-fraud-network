import type { GraphNode } from "../api/types";

/**
 * Node visuals: one glyph and one colour per kind of thing on the canvas. Glyphs are white
 * line drawings on a coloured disc, so they stay legible in light and dark themes. The shape
 * of the glyph carries the meaning; colour only reinforces it (colour-blind safe, TRD 6).
 */

export type VisualKey =
  | "person"
  | "organization"
  | "group"
  | "role_policyholder"
  | "role_insured"
  | "role_claimant"
  | "role_witness"
  | "role_driver"
  | "role_passenger"
  | "claim"
  | "claim_closed"
  | "policy"
  | "vehicle"
  | "property"
  | "legal"
  | "medical"
  | "bodyshop"
  | "record"
  | "address"
  | "phone"
  | "email"
  | "bank_acct"
  | "tax_id"
  | "device"
  | "name"
  | "dob"
  | "loss_date"
  | "fnol_date"
  | "loss_type"
  | "loss_description"
  | "claim_status"
  | "claim_amount"
  | "attribute";

interface Visual {
  label: string;
  color: string;
  /** SVG body on a 24x24 canvas, drawn with a white stroke. */
  glyph: string;
}

export const VISUALS: Record<VisualKey, Visual> = {
  person: {
    label: "Person",
    color: "#0072B2",
    glyph: `<circle cx="12" cy="8" r="4"/><path d="M4.5 21c0-4.2 3.4-7 7.5-7s7.5 2.8 7.5 7"/>`,
  },
  organization: {
    label: "Organization",
    color: "#00796B",
    glyph:
      `<path d="M5 21V4.5A1.5 1.5 0 0 1 6.5 3h11A1.5 1.5 0 0 1 19 4.5V21"/><path d="M3 21h18"/>` +
      `<path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2"/>`,
  },
  group: {
    label: "Group",
    color: "#8A6D00",
    glyph:
      `<circle cx="8" cy="9" r="3"/><circle cx="16.5" cy="9" r="3"/>` +
      `<path d="M2 20c0-3.3 2.7-5.5 6-5.5M22 20c0-3.3-2.7-5.5-5.5-5.5M7.5 20c0-3 2-5 4.5-5s4.5 2 4.5 5"/>`,
  },
  role_policyholder: {
    label: "Policyholder",
    color: "#283593",
    glyph:
      `<circle cx="9.5" cy="8" r="3.5"/><path d="M3 20c0-3.6 2.8-6 6.5-6"/>` +
      `<path d="m17 12 4 1.5v3c0 2.4-1.7 4-4 5-2.3-1-4-2.6-4-5v-3z"/>`,
  },
  role_insured: {
    label: "Insured",
    color: "#0072B2",
    glyph:
      `<path d="M12 2.5 4.5 5.5v6c0 4.6 3.2 8.2 7.5 10 4.3-1.8 7.5-5.4 7.5-10v-6z"/>` +
      `<circle cx="12" cy="10" r="2.4"/><path d="M7.8 17c.5-2.2 2.2-3.3 4.2-3.3s3.7 1.1 4.2 3.3"/>`,
  },
  role_claimant: {
    label: "Claimant",
    color: "#D55E00",
    glyph:
      `<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6"/>` +
      `<path d="M18 5.5v6M18 15.5v.5"/>`,
  },
  role_witness: {
    label: "Witness",
    color: "#CC79A7",
    glyph:
      `<path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/>` +
      `<circle cx="12" cy="12" r="3"/>`,
  },
  role_driver: {
    label: "Driver",
    color: "#009E73",
    glyph:
      `<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.2"/>` +
      `<path d="M3.5 10.5 10 11.5M20.5 10.5 14 11.5M12 14.2V21"/>`,
  },
  role_passenger: {
    label: "Passenger",
    color: "#56B4E9",
    glyph:
      `<circle cx="12" cy="6.5" r="3"/><path d="M6 21v-4a3 3 0 0 1 3-3h6a3 3 0 0 1 3 3v4"/>` +
      `<path d="m8 14 8 7"/>`,
  },
  // A plain document: green while the claim is open, grey once it is closed.
  claim: {
    label: "Claim (open)",
    color: "#2E7D32",
    glyph: `<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>`,
  },
  claim_closed: {
    label: "Claim (closed)",
    color: "#757575",
    glyph: `<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>`,
  },
  policy: {
    label: "Policy",
    color: "#3949AB",
    glyph: `<path d="M12 3 5 6v5.5c0 4.4 3 8 7 9.5 4-1.5 7-5.1 7-9.5V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>`,
  },
  vehicle: {
    label: "Vehicle",
    color: "#5D4037",
    glyph:
      `<path d="M4 16v-4l2-5h12l2 5v4z"/><path d="M4 12h16"/><circle cx="8" cy="17" r="1.8"/>` +
      `<circle cx="16" cy="17" r="1.8"/>`,
  },
  property: {
    label: "Property",
    color: "#EF6C00",
    glyph:
      `<path d="M4 21V9l8-6 8 6v12z"/><path d="M9 21v-6h6v6M9 11h1.5M13.5 11H15"/>`,
  },
  legal: {
    label: "Legal representative",
    color: "#6A1B9A",
    glyph:
      `<path d="M12 4v16M7 20h10M5 7h14"/><path d="m5 7-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z"/>`,
  },
  medical: {
    label: "Medical provider",
    color: "#00897B",
    glyph: `<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M12 8v8M8 12h8"/>`,
  },
  bodyshop: {
    label: "Auto body shop",
    color: "#757575",
    glyph:
      `<path d="M14.5 6.5a4 4 0 0 0 5 5L10 21a2.1 2.1 0 0 1-3-3z"/>` +
      `<path d="M14.5 6.5 17 4l3 3-2.5 2.5"/>`,
  },
  record: {
    label: "Source record",
    color: "#546E7A",
    glyph: `<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>`,
  },
  address: {
    label: "Address",
    color: "#C2560D",
    glyph: `<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10.5h13V10"/><path d="M10 20.5V14h4v6.5"/>`,
  },
  phone: {
    label: "Phone",
    color: "#A33F85",
    glyph: `<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18h2"/>`,
  },
  email: {
    label: "Email",
    color: "#6B4FBB",
    glyph: `<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 7 8.5 6 8.5-6"/>`,
  },
  bank_acct: {
    label: "Bank account",
    color: "#2E7D32",
    glyph: `<rect x="2.5" y="5" width="19" height="14" rx="2"/><path d="M2.5 10h19M6 15h4"/>`,
  },
  tax_id: {
    label: "Tax ID",
    color: "#B22B3A",
    glyph:
      `<rect x="3" y="4.5" width="18" height="15" rx="2"/><circle cx="9" cy="11" r="2.3"/>` +
      `<path d="M5.5 16.5c.6-1.8 1.9-2.7 3.5-2.7s2.9.9 3.5 2.7M15 10h3.5M15 14h3.5"/>`,
  },
  device: {
    label: "Device / IP",
    color: "#455A8A",
    glyph: `<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>`,
  },
  name: {
    label: "Name",
    color: "#6D4C41",
    glyph: `<path d="M3.5 12.5V4.5h8l9 9-8 8z"/><circle cx="7.8" cy="8.8" r="1.2"/>`,
  },
  dob: {
    label: "Date of birth",
    color: "#00838F",
    glyph: `<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>`,
  },
  loss_date: {
    label: "Date of loss",
    color: "#C62828",
    glyph: `<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4M12 13v3M12 18.2v.2"/>`,
  },
  fnol_date: {
    label: "First notice of loss",
    color: "#EF6C00",
    glyph: `<path d="M6 17V11a6 6 0 0 1 12 0v6l1.5 2h-15z"/><path d="M10 21h4"/>`,
  },
  loss_type: {
    label: "Claim type",
    color: "#AD1457",
    glyph: `<path d="M3.5 12.5V4.5h8l9 9-8 8z"/><circle cx="7.8" cy="8.8" r="1.2"/>`,
  },
  loss_description: {
    label: "Loss description",
    color: "#546E7A",
    glyph: `<path d="M5 6h14M5 11h14M5 16h9"/>`,
  },
  claim_status: {
    label: "Claim status",
    color: "#2E7D32",
    glyph: `<path d="M6 21V4M6 5h11l-2 4 2 4H6"/>`,
  },
  claim_amount: {
    label: "Claimed amount",
    color: "#00695C",
    glyph: `<circle cx="12" cy="12" r="9"/><path d="M14.5 9c-.5-1-1.4-1.5-2.5-1.5-1.5 0-2.5.8-2.5 2s1 1.7 2.5 2 2.5.8 2.5 2-1 2-2.5 2c-1.2 0-2.1-.6-2.6-1.6M12 6v1.5M12 16.5V18"/>`,
  },
  attribute: {
    label: "Attribute",
    color: "#607D8B",
    glyph: `<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/>`,
  },
};

/** Attribute types the catalog knows (backend/graphy/catalog.py), in legend order. */
export const ATTRIBUTE_KEYS: VisualKey[] = [
  "address",
  "phone",
  "email",
  "bank_acct",
  "tax_id",
  "device",
  "name",
  "dob",
];

const ENTITY_KEY: Record<string, VisualKey> = {
  Organization: "organization", Claim: "claim", Policy: "policy", Vehicle: "vehicle",
  Property: "property", LegalRep: "legal", MedicalProvider: "medical", BodyShop: "bodyshop",
};

/** Icon for an entity type from the API; anything unrecognized is shown as a person. */
export const entityKey = (type: string | null | undefined): VisualKey =>
  ENTITY_KEY[type ?? ""] ?? "person";

/** Roles a person plays, strongest first: the first one a person holds picks their icon. */
export const ROLE_ORDER = [
  "claimant", "insured", "policyholder", "driver", "passenger", "witness",
] as const;
export const ROLE_KEYS: VisualKey[] = ROLE_ORDER.map((r) => `role_${r}` as VisualKey);

/** Legend order for the insurance entity types. */
export const INSURANCE_KEYS: VisualKey[] = [
  "claim", "claim_closed", "policy", "vehicle", "property", "legal", "medical", "bodyshop",
];

export function visualKey(node: Pick<GraphNode, "kind" | "entity_type" | "data">): VisualKey {
  switch (node.kind) {
    case "Entity": {
      const key = entityKey(node.entity_type);
      const status = node.data.claim_status;
      return key === "claim" && typeof status === "string" && /^closed/i.test(status)
        ? "claim_closed"
        : key;
    }
    case "Group":
      return "group";
    case "SourceRecord":
      return "record";
    case "AttributeValue": {
      const t = node.data.attr_type;
      return typeof t === "string" && t in VISUALS ? (t as VisualKey) : "attribute";
    }
    default:
      return "attribute";
  }
}

const svg = (inner: string, stroke: string) =>
  // width/height give the image an intrinsic square size; without them browsers assume 300x150
  // for a data-URI SVG and Cytoscape draws the glyph off-centre and tiny.
  `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="${stroke}" ` +
  `stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;

/** White glyph as a data URI, for use as a Cytoscape background image. */
export const glyphUri = (key: VisualKey): string =>
  `data:image/svg+xml;utf8,${encodeURIComponent(svg(VISUALS[key].glyph, "#ffffff"))}`;

/** The glyph at 62% of the node (as the stylesheet draws it) with a small red "!" on the
 *  bottom-right rim: a claim that has been referred to the special investigation unit. */
export const siuGlyphUri = (key: VisualKey): string => {
  const flag =
    `<circle cx="84" cy="84" r="15" fill="#D32F2F" stroke="#ffffff" stroke-width="3"/>` +
    `<path d="M84 76.5v8" stroke="#ffffff" stroke-width="3.6" stroke-linecap="round"/>` +
    `<circle cx="84" cy="91" r="2.2" fill="#ffffff" stroke="none"/>`;
  const inner =
    `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 100 100">` +
    `<g transform="translate(19 19) scale(2.583)" fill="none" stroke="#ffffff" stroke-width="1.9" ` +
    `stroke-linecap="round" stroke-linejoin="round">${VISUALS[key].glyph}</g>${flag}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(inner)}`;
};

/** Full badge (coloured disc plus glyph) as a data URI, for the legend. */
export const badgeUri = (key: VisualKey): string => {
  const v = VISUALS[key];
  const badge =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">` +
    `<circle cx="16" cy="16" r="16" fill="${v.color}"/>` +
    `<g transform="translate(5 5) scale(0.917)" fill="none" stroke="#ffffff" stroke-width="1.9" ` +
    `stroke-linecap="round" stroke-linejoin="round">${v.glyph}</g></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(badge)}`;
};
