from pydantic import BaseModel

from graphy.catalog import EntityType
from graphy.schemas.rules import RuleSetDocument


class ActiveRules(BaseModel):
    """The rules resolution uses now for one entity type, with scoring filled in for every
    attribute that applies to it."""

    entity_type: EntityType
    name: str  # the published rule set, or "built-in default"
    version: str | None
    document: RuleSetDocument


class SimulateRequest(BaseModel):
    entity_type: EntityType
    document: RuleSetDocument


class SimGroup(BaseModel):
    labels: list[str]  # the entities' names
    records: int


class SimReview(BaseModel):
    label_a: str
    label_b: str
    score: int
    reason: str


class Simulation(BaseModel):
    """What a rule set would do to today's data, compared with what is in place now. Nothing is
    changed."""

    records: int
    entities: int  # entities after resolution
    merged_records: int  # records that would sit in a merged entity
    merge_pairs: int
    review_pairs: int  # pairs for a person, shown as probable aliases
    blocked_by_conflict: int
    no_identity_match: int
    current_entities: int
    changed_groups: int  # merged entities that differ from what is in place now
    merges: list[SimGroup]  # the changed groups, largest first
    reviews: list[SimReview]  # the strongest borderline pairs
