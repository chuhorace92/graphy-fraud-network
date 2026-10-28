"""Rich-text notes: HTML in, sanitized HTML stored, plain text out for lists and the agent.

Notes are written in a browser editor and shown back as HTML, so what is stored is only ever
the result of `clean`: an allow-list of formatting tags, links limited to http, https and
mailto, no scripts, styles, handlers or other attributes.
"""

import html
import re

import nh3

MAX_BODY = 200_000

_TAGS = {
    "p", "div", "br", "hr", "strong", "b", "em", "i", "u", "s", "code", "pre", "blockquote",
    "h1", "h2", "h3", "ul", "ol", "li", "a", "table", "thead", "tbody", "tr", "th", "td",
}
_ATTRIBUTES = {"a": {"href"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"}}
_BREAKS = re.compile(r"</(p|div|li|h[1-3]|tr|blockquote|pre)>|<br\s*/?>|<hr\s*/?>", re.I)


def clean(body: str) -> str:
    return nh3.clean(
        body, tags=_TAGS, attributes=_ATTRIBUTES, url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer", set_tag_attribute_values={"a": {"target": "_blank"}})


def text_of(body: str) -> str:
    """The words of a note, one block per line."""
    spaced = _BREAKS.sub(lambda m: m.group(0) + "\n", body)
    plain = html.unescape(nh3.clean(spaced, tags=set()))
    return "\n".join(line.strip() for line in plain.splitlines() if line.strip())


def title_of(title: str, body: str) -> str:
    """The title given, or the first line of the note."""
    if title.strip():
        return title.strip()[:255]
    first = next(iter(text_of(body).splitlines()), "")
    return (first[:80] or "Untitled")


def preview_of(body: str, limit: int = 160) -> str:
    return " ".join(text_of(body).split())[:limit].rstrip()
