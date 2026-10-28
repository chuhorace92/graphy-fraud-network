"""Compact graph format the front end feeds straight into the renderer (TRD 7)."""

from typing import Any, Literal

from pydantic import BaseModel

NodeKind = Literal["Entity", "Group", "SourceRecord", "AttributeValue", "Cluster"]


class GraphNode(BaseModel):
    id: str
    kind: NodeKind
    label: str
    parent: str | None = None
    entity_type: str | None = None
    score: float | None = None
    status: str | None = None
    data: dict[str, Any] = {}


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    label: str | None = None
    data: dict[str, Any] = {}


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = False


class AttributeVersion(BaseModel):
    attr_type: str
    value_id: str
    display: str
    source_system: str | None
    record_id: str
    first_seen: str | None
    last_seen: str | None
    is_current: bool
    is_hub: bool
    shared_with: int  # other entities holding the same value


class EntityDetail(BaseModel):
    entity_id: str
    entity_type: str
    canonical_name: str | None
    rule_set_version: str | None
    record_count: int
    groups: list[dict[str, Any]]


class MergeExplanation(BaseModel):
    record_id: str
    source_system: str | None
    method: str | None
    score: float | None
    rules_fired: list[str]
    rule_set_version: str | None


class AppearanceLink(BaseModel):
    claim_id: str
    claim: str
    role: str


class AppearanceAttribute(BaseModel):
    attr_type: str
    display: str


class Appearance(BaseModel):
    """One source record of an entity: the name it carried, where it was filed, what it held."""
    record_id: str
    source_system: str | None
    name: str | None
    links: list[AppearanceLink]
    attributes: list[AppearanceAttribute]


class SearchHit(BaseModel):
    entity_id: str
    label: str
    entity_type: str
    matched_on: str
    score: float


class Lead(BaseModel):
    """A starting point for an investigation: an entity ranked by how connected it is."""

    entity_id: str
    label: str
    entity_type: str
    connections: int
    via: list[str]  # what links it: attribute types and relationship types


class Overview(BaseModel):
    """The whole database at a glance."""

    claims: int
    policies: int
    people: int
    companies: int  # organizations and the providers that are businesses
    groups: int  # connected networks of two or more entities
    largest_group: int  # entities in the biggest one
    people_records: int  # source records that describe people
    merged_people: int  # people built from two or more records by entity resolution
    merged_records: int  # how many records those people absorbed


class HitMatch(BaseModel):
    """A piece of data an indicator rests on. `kind`: value (a shared value and who holds it),
    claims (claims two providers share, or a time window), group, person or alias."""

    kind: Literal["value", "claims", "group", "person", "alias"]
    entities: list[str]
    claims: list[str] = []
    attr_type: str | None = None
    value_id: str | None = None
    value: str | None = None  # as shown on the graph; secret values are masked
    note: str = ""


class Hit(BaseModel):
    """One analytics indicator that fired on a network, and who it involves."""

    rule_id: str
    title: str
    severity: Literal["low", "medium", "high"]
    points: int
    detail: str
    entities: list[str]
    condition: str = ""  # the rule's test, in words
    matches: list[HitMatch] = []  # the data it matched


class Network(BaseModel):
    """A connected set of entities: one ring, family or provider cluster."""

    network_id: str
    size: int
    links: int
    types: dict[str, int]  # members per entity type, e.g. {"Person": 7, "Claim": 5}
    aliases: int  # ALIAS_OF links inside the network
    focus_id: str  # the most connected member: open this to see the network
    focus_label: str
    via: list[str]  # attribute and relationship types that hold it together
    score: int  # fraud indicators, 0-100
    severity: Literal["low", "medium", "high"]
    flags: list[str]  # why, in plain words
    hits: list[Hit]  # the same, with the rule behind each and the entities involved
    members: list[str] = []  # entity ids; only filled for a single entity's network


class RulePreviewHit(BaseModel):
    network_id: str
    focus_id: str
    focus_label: str
    size: int
    detail: str


class RulePreview(BaseModel):
    """What a rule would do on today's data, before it is published."""

    networks_checked: int
    networks_hit: int
    examples: list[RulePreviewHit]
