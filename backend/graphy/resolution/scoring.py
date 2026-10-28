"""Pairwise scoring for entity resolution (the levers in schemas.rules.Scoring).

Two source records are compared attribute by attribute. Each attribute that matches earns the
points of its strength; a difference can cost points or forbid the merge. The total, 0 to 100,
with a few guards, decides whether the pair merges, goes to a person, or is left alone. Every
result keeps its per-attribute breakdown, so any decision can be explained.

Pure functions over plain data: no database, so all of it is tested directly.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from rapidfuzz import fuzz

from graphy.catalog import DEFAULT_CATALOG
from graphy.schemas.rules import AttributeScoring, Scoring

LEGAL_SUFFIXES = frozenset({
    "inc", "incorporated", "llc", "ltd", "limited", "co", "company", "corp", "corporation",
    "llp", "lp", "pllc", "pc", "plc", "gmbh", "sa",
})
MIN_TOKEN = 3  # shorter words do not make a name block
SURNAME_ALIKE = 0.8  # a surname one letter off (Smith, Smyth) when the lever allows it

# Nickname -> formal name. Ambiguous ones (Pat, Alex) are left out on purpose.
NICKNAMES = {
    "chris": "christopher", "mike": "michael", "bob": "robert", "rob": "robert",
    "bobby": "robert", "bill": "william", "will": "william", "billy": "william",
    "jim": "james", "jimmy": "james", "liz": "elizabeth", "beth": "elizabeth",
    "betty": "elizabeth", "tom": "thomas", "tommy": "thomas", "joe": "joseph",
    "rick": "richard", "dick": "richard", "kate": "katherine", "katie": "katherine",
    "jen": "jennifer", "jenny": "jennifer", "dave": "david", "steve": "steven",
    "tony": "anthony", "dan": "daniel", "matt": "matthew", "nick": "nicholas",
    "sam": "samuel", "sue": "susan", "pete": "peter", "ben": "benjamin",
}


@dataclass(frozen=True)
class Value:
    """One attribute value of a record. `norm` is None for secret values, which can only be
    compared for equality (their `vid` is a keyed hash)."""

    vid: str
    norm: str | None
    display: str


Record = dict[str, list[Value]]  # attr_type -> values
Pair = tuple[str, str]


@dataclass
class Contribution:
    attr: str
    outcome: str  # match | similar | conflict | ignored
    similarity: float
    points: float
    left: str
    right: str
    merges_alone: bool = False
    blocking: bool = False  # a difference that forbade the merge

    def text(self) -> str:
        label = DEFAULT_CATALOG[self.attr].label if self.attr in DEFAULT_CATALOG else self.attr
        pts = f"{self.points:+.0f}".replace("-", "−")
        match self.outcome:
            case "match":
                tail = "merges on its own" if self.merges_alone else f"{pts} points"
                return f"{label}: exact match ({tail})"
            case "similar":
                return f"{label}: {self.similarity:.0%} similar ({pts} points)"
            case "conflict":
                return f"{label}: differs ({pts} points)" if self.points else f"{label}: differs"
            case _:
                return f"{label}: shared by too many records to count"


@dataclass
class PairScore:
    a: str
    b: str
    score: int
    decision: str  # merge | review | none
    reason: str
    merge_alone: bool = False
    contributions: list[Contribution] = field(default_factory=list)
    code: str = ""  # blocked | no_identity | merge_alone | merge | review | low

    def lines(self) -> list[str]:
        """What decided the score: matches, and differences that cost points or blocked."""
        return [c.text() for c in self.contributions
                if c.outcome != "conflict" or c.points or c.blocking]


def name_key(norm: str, strip_suffixes: bool) -> str:
    """A name as compared: initials joined ("l l c" -> "llc") and, optionally, trailing legal
    suffixes dropped, so "Acme Clinic L.L.C." and "ACME CLINIC" are the same name."""
    tokens: list[str] = []
    singles = ""
    for tok in norm.split():
        if len(tok) == 1:
            singles += tok
            continue
        if singles:
            tokens.append(singles)
            singles = ""
        tokens.append(tok)
    if singles:
        tokens.append(singles)
    if strip_suffixes:
        while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
            tokens.pop()
    return " ".join(tokens)


def similarity(a: str, b: str) -> float:
    """0 to 1; word order does not matter, but a name that merely contains another does not
    count as a match."""
    return fuzz.token_sort_ratio(a, b) / 100


def name_parts_similarity(a: str, b: str, cfg: AttributeScoring) -> float:
    """How alike two person names are by their parts, 0 to 1. The surname must agree (exactly,
    unless the lever allows a close spelling), the first names must agree after nicknames, or
    one must be the other's initial, or be at least `min_similarity` alike; a middle name or
    initial may be on one side only. 0 when they are not the same person's name."""
    pa, pb = a.split(), b.split()
    if len(pa) < 2 or len(pb) < 2:
        return 0.0
    if pa[-1] != pb[-1] and (cfg.surname_exact or similarity(pa[-1], pb[-1]) < SURNAME_ALIKE):
        return 0.0
    fa, fb = pa[0], pb[0]
    if cfg.nicknames:
        fa, fb = NICKNAMES.get(fa, fa), NICKNAMES.get(fb, fb)
    if fa == fb:
        return 1.0
    initial = (len(fa) == 1 and fb.startswith(fa)) or (len(fb) == 1 and fa.startswith(fb))
    if cfg.nicknames and initial:
        return 0.9
    sim = similarity(fa, fb)
    return sim if sim >= cfg.min_similarity else 0.0


def _year_similarity(a: str, b: str) -> float:
    """Dates of birth: the same day is 1, the same year 0.8, anything else 0."""
    if a == b:
        return 1.0
    return 0.8 if len(a) >= 4 and a[:4] == b[:4] and a[:4].isdigit() else 0.0


def _text(attr: str, cfg: AttributeScoring, v: Value) -> str | None:
    if v.norm is None:
        return None
    return name_key(v.norm, cfg.ignore_legal_suffixes) if attr == "name" else v.norm


def _compare(attr: str, cfg: AttributeScoring, left: list[Value], right: list[Value],
             holders: dict[str, int]) -> Contribution | None:
    """None when either record lacks the attribute (nothing to compare)."""
    if not left or not right:
        return None
    best: tuple[float, Value, Value] | None = None
    for a in left:
        for b in right:
            if a.vid == b.vid:
                sim = 1.0
            else:
                ta, tb = _text(attr, cfg, a), _text(attr, cfg, b)
                if ta is None or tb is None:
                    sim = 0.0
                elif cfg.compare == "name_parts":
                    sim = name_parts_similarity(ta, tb, cfg)
                elif cfg.compare == "year":
                    sim = _year_similarity(ta, tb)
                elif cfg.compare == "fuzzy":
                    sim = similarity(ta, tb)
                else:
                    sim = 1.0 if ta == tb else 0.0
            if best is None or sim > best[0]:
                best = (sim, a, b)
    assert best is not None
    sim, a, b = best
    # name_parts applies its own thresholds inside; a year match is worth 0.8 or more.
    needed = (1.0 if cfg.compare == "exact" else 0.8 if cfg.compare == "year" else
              0.01 if cfg.compare == "name_parts" else cfg.min_similarity)
    crowded = cfg.ignore_shared_over is not None and max(
        holders.get(a.vid, 0), holders.get(b.vid, 0)) > cfg.ignore_shared_over
    if sim >= needed:
        if crowded:
            return Contribution(attr, "ignored", sim, 0, a.display, b.display)
        return Contribution(attr, "match" if sim == 1.0 else "similar", sim, 0,
                            a.display, b.display)
    return Contribution(attr, "conflict", sim, 0, a.display, b.display)


def score_pair(a: str, b: str, ra: Record, rb: Record, cfg: Scoring,
               holders: dict[str, int]) -> PairScore:
    """Score two records. `holders` maps each value id to how many records hold it."""
    weights = cfg.weights.model_dump()
    contributions: list[Contribution] = []
    identity = merge_alone = blocked = False
    total = 0.0
    why_blocked = ""
    for attr, lever in cfg.attributes.items():
        counts = lever.strength != "off"
        if not (counts or lever.merge_alone or lever.on_conflict != "ignore"):
            continue
        c = _compare(attr, lever, ra.get(attr, []), rb.get(attr, []), holders)
        if c is None:
            continue
        if c.outcome in ("match", "similar"):
            if counts:
                c.points = weights[lever.strength] * c.similarity
                total += c.points
            if lever.merge_alone and c.outcome == "match":
                merge_alone, c.merges_alone = True, True
            if attr in cfg.identity and (counts or lever.merge_alone):
                identity = True
        elif c.outcome == "conflict":
            if lever.on_conflict == "penalize":
                c.points = -lever.conflict_penalty
                total += c.points
            elif lever.on_conflict == "block":
                blocked = c.blocking = True
                why_blocked = why_blocked or (
                    f"{DEFAULT_CATALOG[attr].label if attr in DEFAULT_CATALOG else attr} differs")
        contributions.append(c)

    score = max(0, min(100, round(total)))
    if blocked:
        decision, code, reason = "none", "blocked", f"Not merged: {why_blocked}"
    elif merge_alone:
        decision, code = "merge", "merge_alone"
        reason = "An exact match on a key that merges on its own"
    elif cfg.require_identity_match and not identity:
        decision, code = "none", "no_identity"
        reason = "No name or TIN match, so it is only a shared detail"
    elif score >= cfg.auto_merge and cfg.merge_by_score:
        decision, code = "merge", "merge"
        reason = f"Score {score} reaches the merge score {cfg.auto_merge}"
    elif score >= cfg.review:
        decision, code = "review", "review"
        reason = (f"Score {score} reaches the review score {cfg.review}" if score < cfg.auto_merge
                  or cfg.merge_by_score else
                  f"Score {score} is high, but a score alone does not merge: a person decides")
    else:
        decision, code = "none", "low"
        reason = f"Score {score} is below the review score {cfg.review}"
    return PairScore(a, b, score, decision, reason, merge_alone, contributions, code)


@dataclass
class Candidates:
    pairs: set[Pair] = field(default_factory=set)
    holders: dict[str, int] = field(default_factory=dict)
    skipped_blocks: int = 0


def _blocking_keys(attr: str, cfg: AttributeScoring, v: Value) -> set[str]:
    text = _text(attr, cfg, v)
    if not text:
        return set()
    tokens = text.split()
    if cfg.compare == "year":
        return {text[:4]}
    if cfg.compare == "name_parts":  # the surname, and the start of the first name
        return {f"s:{tokens[-1][:5]}"} if len(tokens) >= 2 else set()
    if attr == "address":  # house number and the last word (the postcode, usually)
        return {tokens[0], tokens[-1]}
    return {t[:4] for t in tokens if len(t) >= MIN_TOKEN}


def candidate_pairs(records: dict[str, Record], cfg: Scoring, max_block: int) -> Candidates:
    """Pairs worth scoring: records that share a value, or (for fuzzy attributes) the start of
    a word. Blocks larger than `max_block` are skipped, as are values the attribute ignores for
    being shared by too many records."""
    out = Candidates()
    by_value: dict[str, set[str]] = defaultdict(set)
    for rid, rec in records.items():
        for values in rec.values():
            for v in values:
                by_value[v.vid].add(rid)
    out.holders = {vid: len(rids) for vid, rids in by_value.items()}

    def add(block: set[str]) -> None:
        if len(block) > max_block:
            out.skipped_blocks += 1
            return
        out.pairs.update((a, b) for a, b in combinations(sorted(block), 2))

    for attr, lever in cfg.attributes.items():
        if not (lever.strength != "off" or lever.merge_alone):
            continue
        for vid, rids in by_value.items():
            if vid.split(":", 1)[0] != attr or len(rids) < 2:
                continue
            if lever.ignore_shared_over is not None and len(rids) > lever.ignore_shared_over:
                continue
            add(rids)
        if lever.compare in ("fuzzy", "name_parts", "year"):
            blocks: dict[str, set[str]] = defaultdict(set)
            for rid, rec in records.items():
                for v in rec.get(attr, []):
                    for key in _blocking_keys(attr, lever, v):
                        blocks[key].add(rid)
            for rids in blocks.values():
                if len(rids) > 1:
                    add(rids)
    return out


def score_all(records: dict[str, Record], cfg: Scoring, max_block: int
              ) -> tuple[list[PairScore], Candidates]:
    cands = candidate_pairs(records, cfg, max_block)
    scored = [score_pair(a, b, records[a], records[b], cfg, cands.holders)
              for a, b in sorted(cands.pairs)]
    return scored, cands


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def rule_id(attr: str) -> str:
    """The id shown for a merge that one attribute decided: "same-tax-id"."""
    return "same-" + _NON_ALNUM.sub("-", attr.lower().replace("_", "-")).strip("-")
