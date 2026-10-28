"""Synthetic data with planted patterns, for demos and tests (TRD 11, "Performance" testing).

    python -m graphy.scripts.seed_demo --people 400 --rings 4 [--csv out.csv] [--no-load]

Planted on top of background noise:
  * duplicates: one person in two source systems with a name variant, same email -> merge
  * households: 3-6 people sharing an address and surname -> benign group
  * rings: 8-14 people sharing a few addresses and bank accounts, tied to two shell companies
  * a shared office phone on 25+ people -> exceeds the phone hub threshold
  * insurance: policies, vehicles, property, claims with people in roles (insured, claimant,
    driver, passenger, witness) and providers (attorneys, clinics, body shops)
  * staged-collision rings: one attorney, clinic and body shop across many claims, policies taken
    out weeks before the loss, the same people rotating roles, some reappearing as aliases
    (Chris / Christopher, an added middle name) under a different tax ID and email
  * phantom-passenger rings: one car and one policy, many accidents, fresh carloads from one pool
  * provider mills: a clinic and attorney on claims from unrelated people (only they link them)
  * property fraud: one owner, several buildings, each policy bought weeks before a loss
All identifiers are fake; tax IDs use the 9xx range, which is never issued as an SSN.
"""

import argparse
import csv
import itertools
import random
import sys
from datetime import date, timedelta
from typing import Any

FIRST = ["Christopher", "Daniel", "James", "Mary", "Robert", "Patricia", "John", "Jennifer",
         "Michael", "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
         "Joseph", "Jessica", "Thomas", "Sarah", "Carlos", "Maria", "Wei", "Mei", "Ahmed",
         "Fatima", "Olga", "Ivan"]
NICK = {"Christopher": "Chris", "Daniel": "Dan", "James": "Jim", "Robert": "Bob",
        "William": "Bill", "Richard": "Rick", "Elizabeth": "Liz", "Michael": "Mike",
        "Joseph": "Joe", "Thomas": "Tom"}
LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
        "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson", "Anderson", "Taylor",
        "Thomas", "Moore", "Jackson", "Martin", "Lee", "Chen", "Nguyen", "Khan", "Petrov"]
STREETS = ["Oak Street", "Maple Avenue", "Cedar Road", "Pine Lane", "Elm Drive", "Lake Boulevard",
           "Hill Court", "River Road", "Park Place", "Main Street"]
CITIES = ["Springfield, IL 62701", "Riverton, WY 82501", "Fairview, TN 37062",
          "Georgetown, TX 78626", "Salem, OR 97301"]
COMPANY = ["Holdings", "Consulting", "Logistics", "Trading", "Ventures", "Solutions"]
MIDDLE = ["Adam", "Lee", "Marie", "Ray", "Ann", "Paul"]
STATES = ["IL", "WY", "TN", "TX", "OR"]
AS_OF = date(2026, 7, 1)  # policies that ended before this are expired
CARS = [("Honda", "Civic"), ("Toyota", "Camry"), ("Ford", "F-150"), ("Chevrolet", "Malibu"),
        ("Nissan", "Altima"), ("Tesla", "Model 3"), ("BMW", "X5")]
LAW = ["& Associates", "Injury Law", "Legal Group", "Law Offices"]
CLINIC = ["Family Clinic", "Chiropractic", "Physical Therapy", "Medical Center", "Pain Care"]
SHOP = ["Auto Body", "Collision", "Autoworks", "Body & Paint"]

# What happened, how it is tagged and what it cost, by kind of claim. Each entry:
# (tags, descriptions, amount range, days from loss to first notice of loss).
PD, BI = "Property Damage", "Bodily Injury"
LOSS: dict[str, tuple[list[list[str]], list[str], tuple[int, int], tuple[int, int]]] = {
    "collision": ([[PD], [PD], [PD, BI]], [
        "Rear-ended at a red light on {street}", "Side-swipe while changing lanes on {street}",
        "Backed into a pole in a parking lot", "Hit a deer on a rural road",
        "Hail damage to the roof and hood", "Other driver ran a stop sign on {street}"],
        (1_200, 9_500), (0, 6)),
    "home": ([[PD]], [
        "Burst pipe flooded the basement", "Storm damaged the roof and gutters",
        "Break-in, electronics and jewellery taken", "Kitchen grease fire, smoke damage"],
        (3_000, 35_000), (0, 8)),
    "staged": ([[PD, BI]], [
        "Low-speed collision at {street}; all occupants report neck and back pain",
        "Vehicle struck from behind at {street}; several injury claims filed",
        "Intersection collision on {street}; other driver left before police arrived"],
        (18_000, 60_000), (0, 2)),
    "phantom": ([[PD, BI]], [
        "Rear-end collision on {street}; four occupants claim whiplash",
        "Minor collision at {street}; every passenger reports injuries"],
        (22_000, 55_000), (0, 1)),
    "mill": ([[BI], [PD, BI]], [
        "Soft-tissue injury after a minor collision, ongoing physical therapy",
        "Back strain after low-speed impact, weekly treatment billed"],
        (9_000, 32_000), (3, 30)),
    "fire": ([[PD]], [
        "Fire damaged the kitchen and living room", "Water damage after a pipe burst overnight",
        "Electrical fire in the garage"],
        (40_000, 180_000), (0, 3)),
}
STATUS = {"ordinary": ["Closed - paid", "Closed - paid", "Open", "Closed - denied"],
          "suspect": ["Under review", "Under review", "Open", "SIU referral"]}

Row = dict[str, str]
Rel = dict[str, str]


class Gen:
    def __init__(self, seed: int) -> None:
        self.r = random.Random(seed)  # noqa: S311 - synthetic data, not security
        self.n = 0
        self.rows: list[Row] = []
        self.rels: list[Rel] = []

    def key(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n:06d}"

    def day(self, start: int = 2015, end: int = 2026) -> date:
        a, b = date(start, 1, 1), date(end, 6, 30)
        return a + timedelta(days=self.r.randrange((b - a).days))

    def address(self) -> str:
        return (f"{self.r.randint(1, 9999)} {self.r.choice(STREETS)}, "
                f"Apt {self.r.randint(1, 40)}, {self.r.choice(CITIES)}")

    def phone(self) -> str:
        return f"({self.r.randint(201, 989)}) 555-{self.r.randint(0, 9999):04d}"

    def tax_id(self) -> str:
        r = self.r
        return f"9{r.randint(0, 99):02d}-{r.randint(70, 99)}-{r.randint(0, 9999):04d}"

    def bank(self) -> str:
        return f"{self.r.randint(10**9, 10**10 - 1)}"

    def add(self, key: str, etype: str, attr: str, value: str, first: date,
            last: date | None = None) -> None:
        self.rows.append({
            "source_key": key, "entity_type": etype, "attr_type": attr, "value": value,
            "first_seen": first.isoformat(), "last_seen": (last or first).isoformat(),
        })

    def rel(self, a: str, b: str, rel_type: str, when: date) -> None:
        self.rels.append({"from_key": a, "to_key": b, "rel_type": rel_type,
                          "first_seen": when.isoformat(), "last_seen": when.isoformat()})

    def alias(self, p: dict[str, Any], kind: str) -> dict[str, Any]:
        """The same person again: new tax ID, email, phone and bank account (so nothing merges),
        same date of birth and address, and a variant of the name."""
        nick = NICK.get(p["first"])
        first, middle = (nick, None) if kind == "nickname" and nick else (
            p["first"], self.r.choice(MIDDLE))
        name = f"{first} {middle} {p['last']}" if middle else f"{first} {p['last']}"
        a = dict(p, key=self.key("ALIAS-"), tax_id=self.tax_id(), name=name,
                 phone=self.phone(), bank=self.bank(),
                 email=f"{first.lower()}{self.r.randint(1, 999)}@example.net")
        self.emit_person(a, name=name)
        return a

    def provider(self, etype: str, words: list[str]) -> str:
        key = self.key("PRV-")
        seen = self.day(2015, 2022)
        self.add(key, etype, "name", f"{self.r.choice(LAST)} {self.r.choice(words)}", seen)
        self.add(key, etype, "tax_id", self.tax_id(), seen)
        self.add(key, etype, "address", self.address(), seen)
        self.add(key, etype, "phone", self.phone(), seen)
        return key

    def policy(self, holder: dict[str, Any], vehicle: bool = True, start: date | None = None,
               address: str | None = None) -> dict[str, str]:
        """A policy for the holder, covering a vehicle (or a property). `start` is the date the
        policy began, which is how a claim soon after inception shows up."""
        when = start or self.day(2018, 2025)
        pol = self.key("POL-")
        self.add(pol, "Policy", "name", f"POL-{self.r.randint(10**6, 10**7 - 1)}", when)
        months = self.r.choice([6, 12])
        expiry = when + timedelta(days=round(months * 30.4))
        status = "Expired" if expiry < AS_OF else "Active"
        if self.r.random() < 0.05:
            status = "Cancelled"
        self.add(pol, "Policy", "policy_inception_date", when.isoformat(), when)
        self.add(pol, "Policy", "policy_expiry_date", expiry.isoformat(), when)
        self.add(pol, "Policy", "policy_type", "Auto" if vehicle else "Homeowners", when)
        self.add(pol, "Policy", "policy_term", f"{months} months", when)
        self.add(pol, "Policy", "policy_status", status, when)
        self.rel(holder["key"], pol, "policyholder", when)
        out = {"policy": pol}
        if vehicle:
            make, model = self.r.choice(CARS)
            car = self.key("VEH-")
            year = self.r.randint(2012, 2025)
            self.add(car, "Vehicle", "name", f"{year} {make} {model}", when)
            self.add(car, "Vehicle", "vehicle_make", make, when)
            self.add(car, "Vehicle", "vehicle_model", model, when)
            self.add(car, "Vehicle", "vehicle_year", str(year), when)
            letters = "".join(self.r.choices("ABCDEFGHJKLMNPRSTUVWXYZ", k=3))
            plate = f"{letters}{self.r.randint(1000, 9999)}"
            self.add(car, "Vehicle", "plate_number", plate, when)
            self.add(car, "Vehicle", "plate_state", self.r.choice(STATES), when)
            self.add(car, "Vehicle", "vin", self.vin(), when)
            out["vehicle"] = car
        else:
            home = self.key("PROP-")
            where = address or holder["address"]
            self.add(home, "Property", "name", f"{where.split(',')[0]} dwelling", when)
            self.add(home, "Property", "address", where, when)
            self.rel(holder["key"], home, "owner", when)
            out["property"] = home
        return out

    def vin(self) -> str:
        return "".join(self.r.choice("ABCDEFGHJKLMNPRSTUVWXYZ0123456789") for _ in range(17))

    def claim_details(self, key: str, kind: str, loss: date) -> None:
        """Date of loss, first notice of loss, type tags, description, status and amount."""
        tags, texts, (lo, hi), (fast, slow) = LOSS[kind]
        notified = loss + timedelta(days=self.r.randint(fast, slow))
        self.add(key, "Claim", "loss_date", loss.isoformat(), notified)
        self.add(key, "Claim", "fnol_date", notified.isoformat(), notified)
        for tag in self.r.choice(tags):
            self.add(key, "Claim", "loss_type", tag, notified)
        street = self.r.choice(STREETS)
        self.add(key, "Claim", "loss_description", self.r.choice(texts).format(street=street),
                 notified)
        suspect = kind in ("staged", "phantom", "mill", "fire")
        self.add(key, "Claim", "claim_status",
                 self.r.choice(STATUS["suspect" if suspect else "ordinary"]), notified)
        self.add(key, "Claim", "claim_amount", f"{self.r.randint(lo, hi):.2f}", notified)
        # Each SIU step only happens if the one before it did.
        referred = self.r.random() < (0.8 if suspect else 0.03)
        accepted = referred and self.r.random() < 0.6
        outcome = accepted and self.r.random() < 0.5
        for attr, yes in (("siu_referred", referred), ("siu_accepted", accepted),
                          ("siu_outcome", outcome)):
            self.add(key, "Claim", attr, "Yes" if yes else "No", notified)

    def claim(self, pol: dict[str, str], when: date, *, insured: dict[str, Any],
              driver: dict[str, Any], claimant: dict[str, Any] | None = None,
              passengers: list[dict[str, Any]] = (), witnesses: list[dict[str, Any]] = (),
              providers: list[tuple[str, str]] = (), kind: str = "collision") -> str:
        c = self.key("CLM-")
        self.add(c, "Claim", "name", f"CLM-{self.r.randint(10**6, 10**7 - 1)}", when)
        self.claim_details(c, kind, when)
        self.rel(c, pol["policy"], "under_policy", when)
        self.rel(c, pol.get("vehicle") or pol["property"], "involves", when)
        self.rel(insured["key"], c, "insured", when)
        self.rel(driver["key"], c, "driver", when)
        if claimant:
            self.rel(claimant["key"], c, "claimant", when)
        for x in passengers:
            self.rel(x["key"], c, "passenger", when)
        for x in witnesses:
            self.rel(x["key"], c, "witness", when)
        for key, rel_type in providers:
            self.rel(key, c, rel_type, when)
        return c

    def person(self, *, first: str | None = None, last: str | None = None,
               address: str | None = None, phone: str | None = None,
               bank: str | None = None, prefix: str = "CRM-") -> dict[str, Any]:
        p = {
            "first": first or self.r.choice(FIRST), "last": last or self.r.choice(LAST),
            "dob": self.day(1950, 2004), "tax_id": self.tax_id(),
            "address": address or self.address(), "phone": phone or self.phone(),
            "bank": bank or self.bank(),
        }
        p["email"] = (f"{p['first'].lower()}.{p['last'].lower()}"
                      f"{self.r.randint(1, 999)}@example.com")
        p["key"] = self.key(prefix)
        self.emit_person(p)
        return p

    def emit_person(self, p: dict[str, Any], name: str | None = None) -> None:
        seen = self.day(2019, 2025)
        k = p["key"]
        self.add(k, "Person", "name", name or f"{p['first']} {p['last']}", seen, date(2026, 6, 1))
        self.add(k, "Person", "dob", p["dob"].isoformat(), seen)
        self.add(k, "Person", "tax_id", p["tax_id"], seen)
        self.add(k, "Person", "email", p["email"], seen, date(2026, 6, 1))
        self.add(k, "Person", "phone", p["phone"], seen, date(2026, 6, 1))
        self.add(k, "Person", "address", p["address"], seen, date(2026, 6, 1))
        self.add(k, "Person", "bank_acct", p["bank"], seen, date(2026, 6, 1))

    def company(self, address: str, phone: str) -> str:
        key = self.key("REG-")
        name = f"{self.r.choice(LAST)} {self.r.choice(COMPANY)} LLC"
        seen = self.day(2024, 2026)
        self.add(key, "Organization", "name", name, seen)
        self.add(key, "Organization", "incorporation_date", seen.isoformat(), seen)
        self.add(key, "Organization", "tax_id", self.tax_id(), seen)
        self.add(key, "Organization", "address", address, seen)
        self.add(key, "Organization", "phone", phone, seen)
        return key


def generate(people: int, rings: int, seed: int = 7) -> list[Row]:
    return generate_all(people, rings, seed)[0]


def generate_all(people: int, rings: int, seed: int = 7) -> tuple[list[Row], list[Rel]]:
    """Attribute rows and relationship rows. Load the rows first: relationships point at them."""
    g = Gen(seed)
    background = [g.person() for _ in range(people)]

    # Address history: older addresses are kept as closed versions (NV-4).
    for p in g.r.sample(background, k=people // 4):
        old = g.day(2012, 2018)
        g.add(p["key"], "Person", "address", g.address(), old, old + timedelta(days=700))

    # Duplicates across source systems, with a nickname, merged on shared email.
    for p in g.r.sample(background, k=people // 10):
        dup = dict(p, key=g.key("LOANS-"))
        g.emit_person(dup, name=f"{NICK.get(p['first'], p['first'])} {p['last']}".upper())

    for _ in range(max(1, people // 40)):  # households
        surname, addr, phone = g.r.choice(LAST), g.address(), g.phone()
        for _ in range(g.r.randint(3, 6)):
            g.person(last=surname, address=addr, phone=phone)

    # Ordinary providers are handed out round-robin so none ends up on dozens of claims by
    # chance; that would fuse every ordinary claim into one network and hide the cases below.
    n_prov = max(4, people // 2)
    lawyer_pool = itertools.cycle([g.provider("LegalRep", LAW) for _ in range(n_prov)])
    clinic_pool = itertools.cycle([g.provider("MedicalProvider", CLINIC) for _ in range(n_prov)])
    shop_pool = itertools.cycle([g.provider("BodyShop", SHOP) for _ in range(n_prov)])

    # Ordinary claims: the policyholder drives, the claimant and any witness are people seen once,
    # and providers are spread thinly, so ordinary claims stay small, separate networks.
    for holder in g.r.sample(background, k=people // 4):
        pol = g.policy(holder)
        for _ in range(g.r.randint(1, 2)):
            claimant = g.person(prefix="CLM-")
            g.claim(
                pol, g.day(2022, 2026), insured=holder, driver=holder, claimant=claimant,
                witnesses=[g.person(prefix="CLM-")] if g.r.random() < 0.4 else [],
                providers=[(next(shop_pool), "repaired_for")]
                + ([(next(clinic_pool), "treated_for")] if g.r.random() < 0.3 else [])
                + ([(next(lawyer_pool), "represents")] if g.r.random() < 0.2 else []),
            )

    for holder in g.r.sample(background, k=max(2, people // 10)):  # homeowner claims
        g.claim(g.policy(holder, vehicle=False), g.day(2023, 2026), insured=holder,
                driver=holder, witnesses=[], kind="home",
                providers=[(next(shop_pool), "repaired_for")])

    # Aliases in the background: Chris/Christopher, or a middle name added.
    for p in g.r.sample(background, k=max(2, people // 20)):
        g.alias(p, g.r.choice(["nickname", "middle"]))

    for ring_no in range(rings):
        addrs = [g.address() for _ in range(g.r.randint(2, 3))]
        banks = [g.bank() for _ in range(g.r.randint(1, 2))]
        # Some members share the ring's address or account; most keep their own, as in real rings.
        members = [
            g.person(address=g.r.choice(addrs) if g.r.random() < 0.5 else None,
                     bank=g.r.choice(banks) if g.r.random() < 0.4 else None, prefix="APP-")
            for _ in range(g.r.randint(8, 14))
        ]
        for _ in range(2):  # shell companies at the ring's addresses
            g.company(g.r.choice(addrs), g.phone())
        lawyer, clinic, shop = (g.provider("LegalRep", LAW), g.provider("MedicalProvider", CLINIC),
                                g.provider("BodyShop", SHOP))
        providers = [(lawyer, "represents"), (clinic, "treated_for"), (shop, "repaired_for")]
        base = date(2025, 9, 1) + timedelta(days=g.r.randrange(150))
        aliases = [g.alias(members[0], "nickname"), g.alias(members[1], "middle")]

        if ring_no % 2 == 0:
            # Staged collisions: a new policy for each claim, taken out weeks before the loss, with
            # the same few people rotating through the roles and two reappearing as aliases.
            for _ in range(g.r.randint(5, 7)):
                loss = base + timedelta(days=g.r.randrange(75))
                insured, driver, claimant = g.r.sample(members, k=3)
                pool = [m for m in members if m not in (insured, driver, claimant)]
                pol = g.policy(insured, start=loss - timedelta(days=g.r.randint(12, 50)))
                g.claim(pol, loss, insured=insured, driver=driver, claimant=claimant,
                        passengers=g.r.sample(pool, k=2),
                        witnesses=[g.r.choice([*pool, *aliases])], providers=providers,
                        kind="staged")
        else:
            # Phantom passengers: one car, one policy, many "accidents", each with a fresh carload
            # drawn from the same pool who all end up at the same clinic and attorney.
            insured = members[0]
            pol = g.policy(insured, start=base - timedelta(days=30))
            for _ in range(g.r.randint(6, 7)):
                crowd = g.r.sample(members[1:] + aliases, k=4)
                g.claim(pol, base + timedelta(days=g.r.randrange(60)), insured=insured,
                        driver=insured, claimant=crowd[0], passengers=crowd[1:],
                        providers=providers, kind="phantom")

    # Provider mills: a clinic and attorney on claims from unrelated people over many months. Only
    # the provider ties them together, which the connection count alone would never single out.
    if rings:
        for _ in range(max(1, rings // 2)):
            clinic, lawyer = g.provider("MedicalProvider", CLINIC), g.provider("LegalRep", LAW)
            for _ in range(7):
                holder = g.person(prefix="CLM-")
                g.claim(g.policy(holder), g.day(2025, 2026), insured=holder, driver=holder,
                        claimant=g.person(prefix="CLM-"),
                        providers=[(clinic, "treated_for"), (lawyer, "represents")],
                        kind="mill")

        # Property fraud: one owner insures several buildings, each policy bought weeks before a
        # fire or water loss, with the same restoration contractor and attorney every time.
        owner, shop, lawyer = g.person(prefix="CLM-"), g.provider("BodyShop", SHOP), g.provider(
            "LegalRep", LAW)
        start = date(2025, 10, 1) + timedelta(days=g.r.randrange(60))
        for i in range(4):
            loss = start + timedelta(days=30 * i + g.r.randrange(20))
            pol = g.policy(owner, vehicle=False, start=loss - timedelta(days=g.r.randint(15, 40)),
                           address=g.address())
            g.claim(pol, loss, insured=owner, driver=owner,
                    providers=[(shop, "repaired_for"), (lawyer, "represents")], kind="fire")

    office = g.phone()  # hub: more people than the phone hub_threshold (20)
    for p in g.r.sample(background, k=min(25, people)):
        g.add(p["key"], "Person", "phone", office, date(2024, 1, 1), date(2026, 6, 1))

    return g.rows, g.rels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--people", type=int, default=400)
    ap.add_argument("--rings", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--csv", help="also write the canonical CSV here ('-' for stdout); "
                                  "relationships go to the same path with .rels.csv")
    ap.add_argument("--no-load", action="store_true", help="only write the CSV")
    args = ap.parse_args()

    rows, rels = generate_all(args.people, args.rings, args.seed)
    if args.csv:
        out = sys.stdout if args.csv == "-" else open(args.csv, "w", newline="")  # noqa: SIM115
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        if out is not sys.stdout:
            out.close()
            with open(f"{args.csv}.rels.csv", "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rels[0]))
                writer.writeheader()
                writer.writerows(rels)
    if args.no_load:
        return

    # Imported here so --no-load works without database drivers configured.
    from graphy.services.jobs import create_job, ingest_rows_now, resolve

    job_id = create_job("ingestion", {"source": "demo", "source_system": "DEMO"}, "seed")
    print("ingest:", ingest_rows_now(job_id, rows, "DEMO"))
    rel_job = create_job("ingestion", {"source": "demo", "layout": "relationships"}, "seed")
    print("relationships:", ingest_rows_now(rel_job, rels, "DEMO"))
    resolution_id = create_job("resolution", {"trigger": "seed"}, "seed")
    resolve(resolution_id)
    print("resolved, job", resolution_id)


if __name__ == "__main__":
    main()
