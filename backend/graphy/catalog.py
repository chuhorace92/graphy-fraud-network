"""Attribute catalog (BRD 9.1, TRD 3.1).

The defaults below mirror the TRD's initial catalog. Published rows in the attribute_type
table override them, so adding or changing an attribute is a data change, not a release.
"""

from enum import StrEnum
from typing import Literal, get_args

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from graphy.db.models import AttributeType

EntityType = Literal[
    "Person", "Organization", "Claim", "Policy", "Vehicle", "Property",
    "LegalRep", "MedicalProvider", "BodyShop",
]
ENTITY_TYPES: tuple[str, ...] = get_args(EntityType)

# Relationship types: rel_type -> (allowed source types, allowed target types). Roles a person
# plays in a claim are relationship types; providers attach to the claims they worked on.
_PROVIDERS = ["LegalRep", "MedicalProvider", "BodyShop"]
REL_TYPES: dict[str, tuple[list[str], list[str]]] = {
    "insured": (["Person"], ["Claim"]),
    "claimant": (["Person"], ["Claim"]),
    "witness": (["Person"], ["Claim"]),
    "driver": (["Person"], ["Claim", "Vehicle"]),
    "passenger": (["Person"], ["Claim", "Vehicle"]),
    "policyholder": (["Person"], ["Policy"]),
    "owner": (["Person", "Organization"], ["Vehicle", "Property"]),
    "under_policy": (["Claim"], ["Policy"]),
    "covers": (["Policy"], ["Vehicle", "Property"]),
    "involves": (["Claim"], ["Vehicle", "Property"]),
    "represents": (["LegalRep"], ["Claim"]),
    "treated_for": (["MedicalProvider"], ["Claim"]),
    "repaired_for": (["BodyShop"], ["Claim"]),
}


class LinkStrength(StrEnum):
    VERY_STRONG = "very_strong"
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    NONE = "none"  # used for matching only, never creates a SHARES link


LINK_WEIGHTS: dict[LinkStrength, float] = {
    LinkStrength.VERY_STRONG: 1.0,
    LinkStrength.STRONG: 0.8,
    LinkStrength.MEDIUM: 0.5,
    LinkStrength.WEAK: 0.3,
    LinkStrength.NONE: 0.0,
}


class Normalizer(BaseModel):
    fn: Literal[
        "e164", "email", "name", "address", "identifier", "date", "device", "text", "amount"
    ]
    default_region: str | None = None


class MatchSpec(BaseModel):
    method: Literal["exact_on_normalized", "fuzzy", "phonetic"] = "exact_on_normalized"
    levels: list[str] = ["exact", "missing"]


class AttributeDefinition(BaseModel):
    attr_type: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    label: str
    applies_to: list[EntityType]
    normalizer: Normalizer
    match: MatchSpec = MatchSpec()
    link_strength: LinkStrength
    hub_threshold: int | None = Field(default=None, ge=2)
    sensitivity: Literal["public", "restricted", "secret"]
    versioning: Literal["stable", "tracked", "multi"]
    canonical_rule: Literal["most_recent", "most_frequent", "source_priority"] = "most_recent"
    # Describes the entity itself (a name, a claim's dates and amount) rather than something it
    # shares with others: never drawn as a node on the canvas, never "shared with" anyone.
    descriptive: bool = False

    @property
    def link_weight(self) -> float:
        return LINK_WEIGHTS[self.link_strength]


_BOTH: list[EntityType] = ["Person", "Organization"]
_PARTIES: list[EntityType] = [*_BOTH, "LegalRep", "MedicalProvider", "BodyShop"]
# People, companies and the providers that are businesses: the parties whose links are counted.
PARTY_TYPES: tuple[str, ...] = tuple(_PARTIES)
_PLACED: list[EntityType] = [*_PARTIES, "Property"]

DEFAULT_CATALOG: dict[str, AttributeDefinition] = {
    d.attr_type: d
    for d in [
        AttributeDefinition(
            attr_type="tax_id", label="SSN / tax ID", applies_to=_PARTIES,
            normalizer=Normalizer(fn="identifier"), link_strength=LinkStrength.VERY_STRONG,
            hub_threshold=None, sensitivity="secret", versioning="stable",
        ),
        AttributeDefinition(
            attr_type="email", label="Email address", applies_to=_PARTIES,
            normalizer=Normalizer(fn="email"), link_strength=LinkStrength.STRONG,
            hub_threshold=25, sensitivity="restricted", versioning="tracked",
        ),
        AttributeDefinition(
            attr_type="phone", label="Phone number", applies_to=_PARTIES,
            normalizer=Normalizer(fn="e164", default_region="US"),
            link_strength=LinkStrength.MEDIUM, hub_threshold=20,
            sensitivity="restricted", versioning="tracked",
        ),
        AttributeDefinition(
            attr_type="address", label="Address", applies_to=_PLACED,
            normalizer=Normalizer(fn="address"), link_strength=LinkStrength.WEAK,
            hub_threshold=30, sensitivity="restricted", versioning="tracked",
        ),
        AttributeDefinition(
            attr_type="device", label="Device / IP", applies_to=["Person"],
            normalizer=Normalizer(fn="device"), link_strength=LinkStrength.MEDIUM,
            hub_threshold=15, sensitivity="restricted", versioning="multi",
        ),
        AttributeDefinition(
            attr_type="bank_acct", label="Bank account", applies_to=_PARTIES,
            normalizer=Normalizer(fn="identifier"), link_strength=LinkStrength.STRONG,
            hub_threshold=None, sensitivity="secret", versioning="stable",
        ),
        AttributeDefinition(
            attr_type="name", label="Name", applies_to=list(ENTITY_TYPES),
            normalizer=Normalizer(fn="name"), match=MatchSpec(method="fuzzy"),
            link_strength=LinkStrength.NONE, sensitivity="restricted",
            versioning="tracked", canonical_rule="most_frequent", descriptive=True,
        ),
        AttributeDefinition(
            attr_type="dob", label="Date of birth", applies_to=["Person"],
            normalizer=Normalizer(fn="date"), link_strength=LinkStrength.NONE,
            sensitivity="restricted", versioning="stable",
        ),
        AttributeDefinition(
            attr_type="incorporation_date", label="Date of incorporation",
            applies_to=["Organization"], normalizer=Normalizer(fn="date"),
            link_strength=LinkStrength.NONE, sensitivity="public", versioning="stable",
            descriptive=True,
        ),
        # Policy and vehicle details. They describe the entity, so none are drawn as nodes.
        *[
            AttributeDefinition(
                attr_type=attr, label=label, applies_to=[etype], normalizer=Normalizer(fn=fn),
                link_strength=LinkStrength.NONE, sensitivity="public", versioning=versioning,
                descriptive=True,
            )
            for etype, attr, label, fn, versioning in [
                ("Policy", "policy_inception_date", "Policy inception date", "date", "stable"),
                ("Policy", "policy_expiry_date", "Policy expiry date", "date", "tracked"),
                ("Policy", "policy_type", "Policy type", "text", "stable"),
                ("Policy", "policy_term", "Policy term", "text", "stable"),
                ("Policy", "policy_status", "Policy status", "text", "tracked"),
                ("Claim", "siu_referred", "Referred to SIU", "text", "tracked"),
                ("Claim", "siu_accepted", "Accepted to SIU", "text", "tracked"),
                ("Claim", "siu_outcome", "SIU outcome", "text", "tracked"),
                ("Vehicle", "plate_state", "Plate state", "text", "tracked"),
                ("Vehicle", "vehicle_make", "Make", "text", "stable"),
                ("Vehicle", "vehicle_model", "Model", "text", "stable"),
                ("Vehicle", "vehicle_year", "Year", "text", "stable"),
            ]
        ],
        AttributeDefinition(  # like the VIN, kept so a plate on two vehicles can be matched
            attr_type="plate_number", label="Plate number", applies_to=["Vehicle"],
            normalizer=Normalizer(fn="identifier"), link_strength=LinkStrength.NONE,
            sensitivity="public", versioning="tracked",
        ),
        # Claim metadata. None of it links entities; it describes the claim and is searchable.
        AttributeDefinition(
            attr_type="loss_date", label="Date of loss", applies_to=["Claim"],
            normalizer=Normalizer(fn="date"), link_strength=LinkStrength.NONE,
            sensitivity="public", versioning="stable",
            descriptive=True,
        ),
        AttributeDefinition(
            attr_type="fnol_date", label="First notice of loss", applies_to=["Claim"],
            normalizer=Normalizer(fn="date"), link_strength=LinkStrength.NONE,
            sensitivity="public", versioning="stable",
            descriptive=True,
        ),
        AttributeDefinition(  # tags: a claim can be Property Damage, Bodily Injury, or both
            attr_type="loss_type", label="Claim type", applies_to=["Claim"],
            normalizer=Normalizer(fn="text"), link_strength=LinkStrength.NONE,
            sensitivity="public", versioning="multi",
            descriptive=True,
        ),
        AttributeDefinition(
            attr_type="loss_description", label="Loss description", applies_to=["Claim"],
            normalizer=Normalizer(fn="text"), link_strength=LinkStrength.NONE,
            sensitivity="restricted", versioning="tracked",
            descriptive=True,
        ),
        AttributeDefinition(
            attr_type="claim_status", label="Claim status", applies_to=["Claim"],
            normalizer=Normalizer(fn="text"), link_strength=LinkStrength.NONE,
            sensitivity="public", versioning="tracked",
            descriptive=True,
        ),
        AttributeDefinition(
            attr_type="claim_amount", label="Claimed amount", applies_to=["Claim"],
            normalizer=Normalizer(fn="amount"), link_strength=LinkStrength.NONE,
            sensitivity="restricted", versioning="tracked",
            descriptive=True,
        ),
        AttributeDefinition(
            attr_type="vin", label="Vehicle VIN", applies_to=["Vehicle"],
            normalizer=Normalizer(fn="identifier"), link_strength=LinkStrength.NONE,
            sensitivity="public", versioning="stable",
        ),
    ]
}


def load_catalog(session: Session | None = None) -> dict[str, AttributeDefinition]:
    """Defaults overlaid with the latest published catalog rows."""
    catalog = dict(DEFAULT_CATALOG)
    if session is None:
        return catalog
    rows = session.scalars(
        select(AttributeType)
        .where(AttributeType.state == "published")
        .order_by(AttributeType.attr_type, AttributeType.version)
    )
    for row in rows:  # later versions overwrite earlier ones
        catalog[row.attr_type] = AttributeDefinition.model_validate(row.definition)
    return catalog
