"""Evaluate analytics rules against one network (GA-1, GA-2).

A rule fires when all of its conditions hold. Each condition is measured on the network's
members, role links and shared values, and names what it found, so a finding reads as
"Acme Clinic (medical provider) and Smith Law (attorney) are together on 4 claims" rather than
a bare number. Pure functions over plain dicts, so they are tested without a database.
"""

import operator
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from typing import Any

from graphy.catalog import DEFAULT_CATALOG
from graphy.schemas.rules import AnalyticsRuleDocument, Condition

# Metrics this engine evaluates per network. The cluster metrics in the schema (density, growth,
# ...) belong to the Phase 2 analytics run and cannot be published as live rules yet.
SUPPORTED_METRICS = {
    "shared_value_holders", "provider_pair_claims", "recurring_group_size",
    "repeat_claim_participants", "alias_pairs", "claims_in_window", "claims_after_policy_start",
}
MAX_MATCHES = 10
DEFAULT_WINDOW_DAYS = 120  # claims_in_window
DEFAULT_NEW_POLICY_DAYS = 60  # claims_after_policy_start
_OP_WORDS = {">=": "at least", ">": "more than", "<=": "at most", "<": "fewer than",
             "==": "exactly"}

POINTS = {"low": 5, "medium": 15, "high": 25}
_OPS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt,
        "==": operator.eq}
_PARTIES = {"Person", "Organization", "LegalRep", "MedicalProvider", "BodyShop"}
_ROLES = {"claimant", "insured", "witness", "driver", "passenger"}
_KIND = {"LegalRep": "attorney", "MedicalProvider": "medical provider", "BodyShop": "body shop"}


@dataclass
class Match:
    """One piece of data a finding rests on. `kind` says what it is: a shared value (`value`) and
    the parties holding it, claims two providers share (`claims`), a group on auto claims
    (`group`), a person's claims (`person`) or a pair of probable aliases (`alias`)."""

    kind: str
    entities: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    attr_type: str | None = None
    value_id: str | None = None
    note: str = ""


@dataclass
class Finding:
    """One indicator that fired: which rule, what it found, and who is involved."""

    rule_id: str
    title: str
    severity: str
    detail: str
    entities: list[str] = field(default_factory=list)
    points: int = 0  # defaults to the severity's points
    condition: str = ""  # the rule's test, in words
    matches: list[Match] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.points = self.points or POINTS[self.severity]


@dataclass
class _Measure:
    value: float
    detail: str
    entities: list[str] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)


def _attr_label(attr: str) -> str:
    return DEFAULT_CATALOG[attr].label.lower() if attr in DEFAULT_CATALOG else attr


def _a(noun: str) -> str:
    return ("an " if noun[0] in "aeiou" else "a ") + noun


def describe(rule: AnalyticsRuleDocument) -> str:
    """The rule's test in plain words: "Fires when at least 2 parties hold the same ..."."""

    def part(c: Condition) -> str:
        words, n = _OP_WORDS[c.op], f"{c.value:g}"
        match c.metric:
            case "shared_value_holders":
                what = _attr_label(c.attr_type) if c.attr_type else "detail"
                return f"{words} {n} parties hold the same {what}"
            case "provider_pair_claims":
                a, b = (_KIND.get(t, t) for t in (c.types or ("provider", "provider")))
                return f"{_a(a)} and {_a(b)} are together on {words} {n} claims"
            case "recurring_group_size":
                return (f"a group of {words} {n} people is on at least {c.min_claims or 2} auto "
                        "claims together, changing roles")
            case "repeat_claim_participants":
                return f"one person is on {words} {n} claims"
            case "alias_pairs":
                noun = "link" if c.value == 1 else "links"
                return f"the network has {words} {n} probable alias {noun}"
            case "claims_in_window":
                days = c.window_days or DEFAULT_WINDOW_DAYS
                return f"{words} {n} claims are filed within {days} days"
            case "claims_after_policy_start":
                return (f"{words} {n} claims are filed within "
                        f"{c.window_days or DEFAULT_NEW_POLICY_DAYS} days of the policy starting")
        return f"{c.metric.replace('_', ' ')} {c.op} {c.value:g}"

    return "Fires when " + " and ".join(part(c) for c in rule.conditions)


def _names(members: dict[str, dict[str, Any]], ids: list[str], cap: int = 3) -> str:
    names = [members[i]["label"] for i in sorted(ids)]
    return ", ".join(names[:cap]) + (f" and {len(names) - cap} more" if len(names) > cap else "")


def _shared_values(c: Condition, members, shares) -> list[_Measure]:
    holders: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in shares:
        if c.attr_type and s["attr_type"] != c.attr_type:
            continue
        for e in (s["a"], s["b"]):
            if members[e]["type"] in _PARTIES:
                holders[(s["attr_type"], s["value_id"])].add(e)
    best: dict[str, set[str]] = {}
    for (attr, _), ents in holders.items():
        if len(ents) > len(best.get(attr, ())):
            best[attr] = ents
    def matched(attr: str) -> list[Match]:
        rows = sorted(((vid, ents) for (a, vid), ents in holders.items()
                       if a == attr and _OPS[c.op](len(ents), c.value)),
                      key=lambda r: (-len(r[1]), r[0]))
        return [Match("value", sorted(ents), attr_type=attr, value_id=vid)
                for vid, ents in rows[:MAX_MATCHES]]

    return [_Measure(len(ents), f"{len(ents)} parties use the same {_attr_label(attr)}"
                     f" ({_names(members, list(ents))})", sorted(ents), matched(attr))
            for attr, ents in sorted(best.items())]


def _claims_by_provider(members, rels) -> dict[str, set[str]]:
    claims = {i for i, m in members.items() if m["type"] == "Claim"}
    out: dict[str, set[str]] = defaultdict(set)
    for r in rels:
        if members[r["src"]]["type"] in _KIND and r["dst"] in claims:
            out[r["src"]].add(r["dst"])
    return out


def _provider_pairs(c: Condition, members, rels) -> list[_Measure]:
    first, second = c.types or ("", "")
    by_provider = _claims_by_provider(members, rels)
    pairs = []
    for a, b in ((x, y) for x in by_provider for y in by_provider):
        if members[a]["type"] == first and members[b]["type"] == second and a != b:
            together = by_provider[a] & by_provider[b]
            if together:
                pairs.append(_Measure(
                    len(together),
                    f"{members[a]['label']} ({_KIND[first]}) and {members[b]['label']} "
                    f"({_KIND[second]}) are together on {len(together)} claims",
                    [a, b, *sorted(together)],
                    [Match("claims", [a, b], sorted(together))]))
    return sorted(pairs, key=lambda m: -m.value)


def _recurring_group(c: Condition, members, rels) -> list[_Measure]:
    """The biggest group of people who keep turning up on the same auto claims, where members
    change roles between claims (driver in one, passenger in the next)."""
    min_claims = c.min_claims or 2
    auto = {r["src"] for r in rels
            if r["rel_type"] == "involves" and members[r["dst"]]["type"] == "Vehicle"}
    on_claim: dict[str, set[str]] = defaultdict(set)  # claim -> people
    roles: dict[str, set[str]] = defaultdict(set)  # person -> roles held
    for r in rels:
        if r["rel_type"] in _ROLES and r["dst"] in auto and members[r["src"]]["type"] == "Person":
            on_claim[r["dst"]].add(r["src"])
            roles[r["src"]].add(r["rel_type"])
    together: Counter[tuple[str, str]] = Counter()
    for people in on_claim.values():
        together.update(combinations(sorted(people), 2))
    parent = {p: p for p in roles}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), n in together.items():
        if n >= min_claims:
            parent[find(a)] = find(b)
    groups: dict[str, set[str]] = defaultdict(set)
    for p in roles:
        groups[find(p)].add(p)
    best: set[str] = set()
    for g in groups.values():
        shifting = [p for p in g if len(roles[p]) >= 2]
        if len(g) > len(best) and len(shifting) >= 2:
            best = g
    if not best:
        return []
    seen = sorted({r for p in best for r in roles[p]})
    claims = sum(1 for people in on_claim.values() if len(people & best) >= 2)
    shared = sorted(c for c, people in on_claim.items() if len(people & best) >= 2)
    return [_Measure(len(best), f"{len(best)} people ({_names(members, list(best))}) share "
                     f"{claims} auto claims, shifting between {', '.join(seen)}", sorted(best),
                     [Match("group", sorted(best), shared)])]


def _day(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _claim_days(members, rels) -> dict[str, date | None]:
    """The day each claim was filed: when its link to its policy was first seen."""
    first: dict[str, Any] = {}
    for r in rels:
        if r["rel_type"] == "under_policy":
            first.setdefault(r["src"], r["first_seen"])
    return {i: _day(first.get(i)) for i, m in members.items() if m["type"] == "Claim"}


def _repeat_participants(c: Condition, members, rels) -> list[_Measure]:
    claims = {i for i, m in members.items() if m["type"] == "Claim"}
    on: dict[str, set[str]] = defaultdict(set)
    for r in rels:
        if r["rel_type"] in _ROLES and r["dst"] in claims and members[r["src"]]["type"] == "Person":
            on[r["src"]].add(r["dst"])
    hit = {p: cl for p, cl in on.items() if _OPS[c.op](len(cl), c.value)}
    if not hit:
        return []
    people = sorted(hit)
    first = members[people[0]]["label"]
    return [_Measure(
        max(len(cl) for cl in hit.values()),
        f"{len(people)} {'person appears' if len(people) == 1 else 'people appear'} on "
        f"{_OP_WORDS[c.op]} {c.value:g} claims, e.g. {first}", people,
        [Match("person", [p], sorted(hit[p])) for p in sorted(hit, key=lambda p: (-len(hit[p]), p))
         [:MAX_MATCHES]])]


def _alias_pairs(c: Condition, aliases) -> list[_Measure]:
    n = len(aliases)
    if not n:
        return []
    return [_Measure(
        n, f"{n} probable alias {'link' if n == 1 else 'links'}: the same person under another "
        "name or ID", sorted({e for pair in aliases for e in pair}),
        [Match("alias", sorted(pair)) for pair in list(aliases)[:MAX_MATCHES]])]


def _claims_in_window(c: Condition, members, rels) -> list[_Measure]:
    window = c.window_days or DEFAULT_WINDOW_DAYS
    dated = sorted((d, i) for i, d in _claim_days(members, rels).items() if d)
    best: tuple[int, int, int] = (0, 0, 0)  # count, span in days, first index
    lo = 0
    for hi, (d, _) in enumerate(dated):
        while (d - dated[lo][0]).days > window:
            lo += 1
        if hi - lo + 1 > best[0]:
            best = (hi - lo + 1, (d - dated[lo][0]).days, lo)
    count, span, start = best
    if not count:
        return []
    inside = sorted(i for _, i in dated[start:start + count])
    every = sorted(i for i, m in members.items() if m["type"] == "Claim")
    return [_Measure(count, f"{count} claims filed within {span} days", every,
                     [Match("claims", claims=inside, note=f"{count} claims within {span} days")])]


def _claims_after_policy_start(c: Condition, members, rels) -> list[_Measure]:
    window = c.window_days or DEFAULT_NEW_POLICY_DAYS
    policy_of = {r["src"]: r["dst"] for r in rels if r["rel_type"] == "under_policy"}
    started = {r["dst"]: _day(r["first_seen"]) for r in rels if r["rel_type"] == "policyholder"}
    quick: dict[str, int] = {}
    for claim, filed in _claim_days(members, rels).items():
        began = started.get(policy_of.get(claim, ""))
        if filed and began and 0 <= (filed - began).days <= window:
            quick[claim] = (filed - began).days
    if not quick:
        return []
    return [_Measure(
        len(quick), f"{len(quick)} claims filed within {window} days of the policy starting",
        sorted(quick),
        [Match("claims", [policy_of[cl]], [cl], note=f"filed {n} days after the policy started")
         for cl, n in sorted(quick.items(), key=lambda kv: kv[1])[:MAX_MATCHES]])]


def _measure(c: Condition, members, rels, shares, aliases) -> list[_Measure]:
    match c.metric:
        case "repeat_claim_participants":
            return _repeat_participants(c, members, rels)
        case "alias_pairs":
            return _alias_pairs(c, aliases)
        case "claims_in_window":
            return _claims_in_window(c, members, rels)
        case "claims_after_policy_start":
            return _claims_after_policy_start(c, members, rels)
        case "shared_value_holders":
            return _shared_values(c, members, shares)
        case "provider_pair_claims":
            return _provider_pairs(c, members, rels)
        case "recurring_group_size":
            return _recurring_group(c, members, rels)
    return []  # cluster metrics from the Phase 2 analytics run are evaluated elsewhere


def unsupported(rule: AnalyticsRuleDocument) -> list[str]:
    """Metrics in the rule that the engine cannot evaluate."""
    return sorted({c.metric for c in rule.conditions} - SUPPORTED_METRICS)


def _points(rule: AnalyticsRuleDocument, m: _Measure) -> int:
    """What a finding adds: the rule's points (or its severity's), or, for a rule that scales,
    its points for each thing named, up to that cap. 0 means the severity's points."""
    if rule.points_each:
        return min(rule.points or POINTS[rule.severity], rule.points_each * max(1, len(m.entities)))
    return rule.points or 0


def evaluate(rules: list[AnalyticsRuleDocument], members: dict[str, dict[str, Any]],
             rels: list[dict[str, Any]], shares: list[dict[str, Any]],
             aliases: list[tuple[str, str]] | None = None) -> list[Finding]:
    """Findings for every rule whose conditions all hold, strongest first. `aliases` are the
    entity pairs the network's alias links join."""
    out: list[Finding] = []
    for rule in rules:
        passing = [[m for m in _measure(c, members, rels, shares, aliases or [])
                    if _OPS[c.op](m.value, c.value)] for c in rule.conditions]
        if passing and all(passing):
            title = rule.description or rule.rule_id
            out += [Finding(rule.rule_id, title, rule.severity, m.detail, m.entities,
                            points=_points(rule, m), condition=describe(rule), matches=m.matches)
                    for m in passing[0][:3]]
    return sorted(out, key=lambda f: -f.points)
