"""Rule documents. Both kinds are typed JSON, validated here and compiled server-side, so no
user-supplied text is ever executed as Cypher (TRD 5, input safety)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from graphy.catalog import EntityType

_ID = r"^[a-z0-9][a-z0-9_-]{1,127}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Entity resolution rule set (ER-1..ER-5, TRD 4 "Rule configuration") -------------------


class BlockingKey(_Strict):
    name: str
    attrs: list[str] = Field(min_length=1)
    transform: Literal["exact", "phonetic", "prefix3", "year"] = "exact"


class Comparison(_Strict):
    attr_type: str
    function: Literal["exact", "jaro_winkler", "levenshtein", "token_set", "date_distance"]
    # Similarity cut-offs from strictest to loosest, each with a match weight.
    levels: list[tuple[float, float]] = Field(min_length=1)


class Thresholds(_Strict):
    auto_merge: float = Field(ge=0, le=1)
    review: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> "Thresholds":
        if self.review > self.auto_merge:
            raise ValueError("review threshold must not exceed auto_merge")
        return self


class DeterministicRule(_Strict):
    rule_id: str = Field(pattern=_ID)
    attrs: list[str] = Field(min_length=1)


class GroupRule(_Strict):
    rule_id: str = Field(pattern=_ID)
    group_type: Literal["Household", "Company"]
    role: str
    shared_attrs: list[str] = []
    relationship_types: list[str] = []
    same_surname: bool = False
    min_score: float = Field(default=0.0, ge=0, le=1)
    max_group_size: int = Field(default=50, ge=2)


class Constraints(_Strict):
    max_cluster_size: int = Field(default=50, ge=2)
    max_block_size: int = Field(default=1_000, ge=2)


Strength = Literal["off", "low", "medium", "strong"]
# Everything a pair of records can be compared on, across the entity types; a type only has
# values for the ones that apply to it (see ATTRIBUTES_BY_TYPE).
SCORED_ATTRIBUTES = (
    "tax_id", "name", "dob", "incorporation_date", "email", "phone", "address", "device",
    "bank_acct", "vin", "plate_number",
)
PARTY_ATTRS = ("tax_id", "name", "email", "phone", "address", "bank_acct")
ATTRIBUTES_BY_TYPE: dict[str, tuple[str, ...]] = {
    "Person": ("tax_id", "name", "dob", "email", "phone", "address", "device", "bank_acct"),
    "Organization": (*PARTY_ATTRS[:2], "incorporation_date", *PARTY_ATTRS[2:]),
    "Vehicle": ("vin", "plate_number", "name"),
    "LegalRep": PARTY_ATTRS,
    "MedicalProvider": PARTY_ATTRS,
    "BodyShop": PARTY_ATTRS,
}
# What says who a record is: a match on one of these is an "identity match".
IDENTITY_BY_TYPE: dict[str, list[str]] = {
    "Vehicle": ["vin", "plate_number"],
}
DEFAULT_IDENTITY = ["tax_id", "name"]
Compare = Literal["exact", "fuzzy", "name_parts", "year"]


class AttributeScoring(_Strict):
    """The levers for one attribute: whether it counts, how it is compared, and what a
    difference means."""

    strength: Strength = "off"  # how many points a match is worth (see ScoringWeights)
    # exact: the same value. fuzzy: alike enough (names, addresses). name_parts: a person's name
    # by its parts (surname, first name, nicknames). year: dates of birth that agree on the year.
    compare: Compare = "exact"
    min_similarity: float = Field(default=0.88, ge=0.5, le=1.0)  # fuzzy; first name for name_parts
    surname_exact: bool = True  # name_parts: the surname must be the same
    nicknames: bool = True  # name_parts: Chris is Christopher, J is John
    on_conflict: Literal["ignore", "penalize", "block"] = "ignore"  # both have a value, no match
    conflict_penalty: int = Field(default=20, ge=0, le=100)
    merge_alone: bool = False  # an exact match on this alone merges the records
    ignore_shared_over: int | None = Field(default=None, ge=2)  # skip values held by more records
    ignore_legal_suffixes: bool = True  # names: Inc, LLC, Co... do not count


class ScoringWeights(_Strict):
    strong: int = Field(default=50, ge=0, le=100)
    medium: int = Field(default=25, ge=0, le=100)
    low: int = Field(default=10, ge=0, le=100)


class Scoring(_Strict):
    """How a pair of records becomes a score from 0 to 100, and what the score decides."""

    weights: ScoringWeights = ScoringWeights()
    attributes: dict[str, AttributeScoring] = {}
    auto_merge: int = Field(default=95, ge=0, le=100)  # at or above: merge (if merge_by_score)
    review: int = Field(default=60, ge=0, le=100)  # at or above: a person decides
    # When off, a score never merges records on its own: a high score goes to a person, and only
    # a key that merges alone (a tax ID) or a person's decision merges.
    merge_by_score: bool = True
    # A shared bank account, email or phone is the signal this tool exists to surface. Unless one
    # of `identity` also matches, such a pair is never merged or queued, however high it scores.
    require_identity_match: bool = True
    identity: list[str] = DEFAULT_IDENTITY

    @model_validator(mode="after")
    def _valid(self) -> "Scoring":
        unknown = sorted((set(self.attributes) | set(self.identity)) - set(SCORED_ATTRIBUTES))
        if unknown:
            raise ValueError(f"cannot score {', '.join(unknown)}")
        if self.review > self.auto_merge:
            raise ValueError("the review score must not exceed the merge score")
        return self


class RuleSetDocument(_Strict):
    standardization: dict[str, dict[str, str]] = {}
    blocking: list[BlockingKey] = []
    comparisons: list[Comparison] = []
    thresholds: Thresholds = Thresholds(auto_merge=0.95, review=0.80)
    deterministic_rules: list[DeterministicRule] = []  # before scoring: merge on an exact key
    scoring: Scoring | None = None
    group_rules: list[GroupRule] = []
    constraints: Constraints = Constraints()


def _keys(*attrs: str) -> dict[str, AttributeScoring]:
    return {a: AttributeScoring(strength="strong", merge_alone=True) for a in attrs}


# What each type starts with. A tax ID, an email or a VIN merges records on its own, exactly as
# before scoring existed. For people the rest of the details are scored, so a name variant on the
# same date of birth, or a shared phone or address on top of one, is put to a person as a
# probable alias instead of being merged: score alone never merges people by default.
_PERSON = Scoring(
    attributes={
        **_keys("tax_id", "email"),
        "name": AttributeScoring(strength="medium", compare="name_parts", min_similarity=0.8),
        "dob": AttributeScoring(strength="strong"),
        "phone": AttributeScoring(strength="medium", ignore_shared_over=20),
        "address": AttributeScoring(strength="low", compare="fuzzy", min_similarity=0.9,
                                    ignore_shared_over=30),
        "device": AttributeScoring(strength="medium", ignore_shared_over=20),
        "bank_acct": AttributeScoring(strength="strong"),
    },
    merge_by_score=False,
)
_BUSINESS = Scoring(attributes={**_keys("tax_id", "email"), "name": AttributeScoring()},
                    merge_by_score=False)
_VEHICLE = Scoring(attributes={"vin": AttributeScoring(strength="strong", merge_alone=True),
                               "plate_number": AttributeScoring(strength="medium")},
                   merge_by_score=False, identity=IDENTITY_BY_TYPE["Vehicle"])
DEFAULT_SCORING_BY_TYPE: dict[str, Scoring] = {
    "Person": _PERSON, "Organization": _BUSINESS, "Vehicle": _VEHICLE,
    "LegalRep": _BUSINESS, "MedicalProvider": _BUSINESS, "BodyShop": _BUSINESS,
}


def default_rule_set(entity_type: str) -> RuleSetDocument:
    """The rules a type uses until one is published. Types nothing is compared on (claims,
    policies, property) never merge."""
    return RuleSetDocument(scoring=DEFAULT_SCORING_BY_TYPE.get(entity_type, Scoring()))


def effective_scoring(doc: RuleSetDocument) -> Scoring:
    """The scoring a rule set stands for. A rule set written before scoring existed merged on
    exact keys only; that is the same as scoring with those keys set to merge alone and nothing
    else counting."""
    if doc.scoring is not None:
        return doc.scoring
    keys = {r.attrs[0] for r in doc.deterministic_rules
            if len(r.attrs) == 1 and r.attrs[0] in SCORED_ATTRIBUTES}
    return Scoring(attributes=_keys(*sorted(keys)), auto_merge=100, review=100,
                   merge_by_score=False, require_identity_match=False)


def filled_scoring(doc: RuleSetDocument, entity_type: str) -> Scoring:
    """The scoring with a row for every attribute that applies to the type, so a screen can
    show a lever for each (off ones included)."""
    scoring = effective_scoring(doc)
    applies = ATTRIBUTES_BY_TYPE.get(entity_type, ())
    return scoring.model_copy(update={"attributes": {
        a: scoring.attributes.get(a, AttributeScoring()) for a in applies}})


class RuleSetCreate(_Strict):
    name: str = Field(pattern=_ID)
    entity_type: EntityType
    document: RuleSetDocument


# --- Analytics rules (GA-1, GA-2, TRD 5 "Rule definition") --------------------------------

Metric = Literal[
    "distinct_members",
    "shared_attribute_count",
    "age_span_days",
    "density",
    "growth_30d",
    "risk_flag_share",
    "max_degree",
    # Pattern metrics, evaluated per network (see services/rules_engine.py):
    "shared_value_holders",  # most parties holding one value of attr_type (any attribute if unset)
    "provider_pair_claims",  # claims where one provider of each of `types` appear together
    "recurring_group_size",  # people who share >= min_claims auto claims, with shifting roles
    "repeat_claim_participants",  # the most claims one person is on, in any role
    "alias_pairs",  # probable-alias links inside the network
    "claims_in_window",  # the most claims filed inside `window_days` of each other
    "claims_after_policy_start",  # claims filed within `window_days` of their policy starting
]


class Condition(_Strict):
    metric: Metric
    op: Literal[">=", ">", "<=", "<", "=="]
    value: float
    attr_type: str | None = None
    types: list[str] | None = None  # provider_pair_claims: the two entity types that pair up
    min_claims: int | None = Field(default=None, ge=2)  # recurring_group_size
    window_days: int | None = Field(default=None, ge=1, le=3650)  # the two timing metrics

    @model_validator(mode="after")
    def _pattern_args(self) -> "Condition":
        if self.metric == "provider_pair_claims" and (not self.types or len(self.types) != 2):
            raise ValueError("provider_pair_claims needs types: [first, second]")
        return self


class AnalyticsRuleDocument(_Strict):
    rule_id: str = Field(pattern=_ID)
    scope: Literal["cluster", "entity"]
    conditions: list[Condition] = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    description: str | None = None
    # Points added to a network's score when the rule fires; by default what its severity is
    # worth (low 5, medium 15, high 25).
    points: int | None = Field(default=None, ge=1, le=50)
    # With this set, points grow with what the rule found: this many for each person, claim or
    # pair it names, up to `points` (or the severity's points).
    points_each: int | None = Field(default=None, ge=1, le=50)


# The detection rules every install starts with. init_db stores them as published rules, where
# they can be edited (a new version) without a release; this list is the fallback and the seed.
DEFAULT_ANALYTICS_RULES: list[AnalyticsRuleDocument] = [
    AnalyticsRuleDocument(
        rule_id="shared-attribute-two-parties", scope="cluster", severity="low",
        description="Two or more parties use the same phone, address, account or device.",
        conditions=[Condition(metric="shared_value_holders", op=">=", value=2)],
    ),
    AnalyticsRuleDocument(
        rule_id="medical-and-legal-on-three-claims", scope="cluster", severity="high",
        description="The same medical provider and legal representative are on 3 or more claims "
                    "together.",
        conditions=[Condition(metric="provider_pair_claims", op=">=", value=3,
                              types=["MedicalProvider", "LegalRep"])],
    ),
    AnalyticsRuleDocument(
        rule_id="legal-and-bodyshop-on-three-claims", scope="cluster", severity="high",
        description="The same legal representative and auto body shop are on 3 or more claims "
                    "together.",
        conditions=[Condition(metric="provider_pair_claims", op=">=", value=3,
                              types=["LegalRep", "BodyShop"])],
    ),
    AnalyticsRuleDocument(
        rule_id="same-group-shifting-roles-auto-claims", scope="cluster", severity="high",
        description="The same group of 3 or more people is on multiple auto claims, switching "
                    "between roles such as driver, passenger and claimant.",
        conditions=[Condition(metric="recurring_group_size", op=">=", value=3, min_claims=2)],
    ),
    # What were hard-coded indicators are rules too, so each can be tested, re-weighted or retired.
    AnalyticsRuleDocument(
        rule_id="repeat-participants", scope="cluster", severity="medium", points=20, points_each=5,
        description="The same people appear on 3 or more claims",
        conditions=[Condition(metric="repeat_claim_participants", op=">=", value=3)],
    ),
    AnalyticsRuleDocument(
        rule_id="probable-aliases", scope="cluster", severity="medium",
        description="The same person appears under another name or ID",
        conditions=[Condition(metric="alias_pairs", op=">=", value=1)],
    ),
    AnalyticsRuleDocument(
        rule_id="claims-bunched-in-time", scope="cluster", severity="medium",
        description="4 or more claims within 120 days",
        conditions=[Condition(metric="claims_in_window", op=">=", value=4, window_days=120)],
    ),
    AnalyticsRuleDocument(
        rule_id="claims-soon-after-policy-start", scope="cluster", severity="medium",
        description="Claims within 60 days of the policy starting",
        conditions=[Condition(metric="claims_after_policy_start", op=">=", value=2,
                              window_days=60)],
    ),
]
