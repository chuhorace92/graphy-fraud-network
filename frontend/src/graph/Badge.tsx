import { badgeUri, type VisualKey } from "./icons";

/** The coloured icon disc used on the canvas, for use in lists and headers. */
export function Badge({ k, size = 24 }: { k: VisualKey; size?: number }) {
  return <img className="badge" src={badgeUri(k)} alt="" width={size} height={size} />;
}
