"""Attribute standardization (ER-10, TRD 4 step 1). Raw and normalized values are both kept."""

import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import phonenumbers

from graphy.catalog import AttributeDefinition


class NormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedValue:
    value_id: str  # stable AttributeValue.id, derived from the hash
    raw: str | None  # None for secret attributes
    normalized: str | None  # None for secret attributes
    hash: str
    display: str  # what the UI shows; masked for secret attributes


_ADDRESS_ABBREVIATIONS = {
    "STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "BOULEVARD": "BLVD", "DRIVE": "DR",
    "LANE": "LN", "COURT": "CT", "PLACE": "PL", "APARTMENT": "APT", "SUITE": "STE",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "FLOOR": "FL",
}


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _name(raw: str) -> str:
    text = _strip_accents(raw).casefold()
    text = re.sub(r"[^\w\s'-]", " ", text)
    return " ".join(text.split())


def _address(raw: str) -> str:
    text = _strip_accents(raw).upper()
    text = re.sub(r"[^\w\s#]", " ", text)
    return " ".join(_ADDRESS_ABBREVIATIONS.get(tok, tok) for tok in text.split())


def _email(raw: str) -> str:
    text = raw.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
        raise NormalizationError("not an email address")
    return text


def _e164(raw: str, region: str | None) -> str:
    try:
        number = phonenumbers.parse(raw, region or "US")
    except phonenumbers.NumberParseException as exc:
        raise NormalizationError(f"unparseable phone number: {exc}") from exc
    if not phonenumbers.is_possible_number(number):
        raise NormalizationError("impossible phone number")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def _identifier(raw: str) -> str:
    text = re.sub(r"[^0-9A-Za-z]", "", raw).upper()
    if not text:
        raise NormalizationError("empty identifier")
    return text


def _date(raw: str) -> str:
    try:
        return date.fromisoformat(raw.strip()).isoformat()
    except ValueError as exc:
        raise NormalizationError("date must be ISO 8601 (YYYY-MM-DD)") from exc


def _device(raw: str) -> str:
    return raw.strip().lower()


def _text(raw: str) -> str:
    return " ".join(raw.split()).casefold()


def _amount(raw: str) -> str:
    try:
        return f"{Decimal(re.sub(r'[^0-9.]', '', raw)):.2f}"
    except InvalidOperation as exc:
        raise NormalizationError("not an amount") from exc


def standardize(defn: AttributeDefinition, raw: str) -> str:
    if raw is None or not raw.strip():
        raise NormalizationError("empty value")
    match defn.normalizer.fn:
        case "name":
            out = _name(raw)
        case "address":
            out = _address(raw)
        case "email":
            out = _email(raw)
        case "e164":
            out = _e164(raw, defn.normalizer.default_region)
        case "identifier":
            out = _identifier(raw)
        case "date":
            out = _date(raw)
        case "device":
            out = _device(raw)
        case "text":
            out = _text(raw)
        case "amount":
            out = _amount(raw)
    if not out:
        raise NormalizationError("value is empty after normalization")
    return out


def _mask(value: str) -> str:
    return f"•••{value[-4:]}" if len(value) > 4 else "••••"


def normalize(defn: AttributeDefinition, raw: str, hash_key: str) -> NormalizedValue:
    normalized = standardize(defn, raw)
    digest = hmac.new(
        hash_key.encode(), f"{defn.attr_type}:{normalized}".encode(), hashlib.sha256
    ).hexdigest()
    value_id = f"{defn.attr_type}:{digest[:40]}"
    if defn.sensitivity == "secret":
        return NormalizedValue(value_id, None, None, digest, _mask(normalized))
    # Free text and money show as written or formatted, not as the lowercased match key.
    match defn.normalizer.fn:
        case "text":
            display = " ".join(raw.split())
        case "amount":
            display = f"${Decimal(normalized):,.2f}"
        case _:
            display = normalized
    return NormalizedValue(value_id, raw.strip(), normalized, digest, display)
