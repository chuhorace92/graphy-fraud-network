const ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;" };

/** Plain text as note HTML: one paragraph per line, markup escaped. */
export function textToHtml(text: string): string {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => `<p>${l.replace(/[&<>]/g, (c) => ESCAPES[c])}</p>`)
    .join("");
}

/** Whether the editor's HTML holds any words. */
export function hasText(html: string): boolean {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return (doc.body.textContent ?? "").trim().length > 0;
}
