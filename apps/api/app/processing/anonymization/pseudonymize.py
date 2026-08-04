"""Request-scoped consistent pseudonymization. Mappings never leave the request."""

from __future__ import annotations

import hashlib

from app.processing.detection.types import EntityType
from app.recognizers.checksums import digits_only, luhn_valid, make_valid_sin

_FIRST_NAMES = (
    "Jordan",
    "Riley",
    "Casey",
    "Avery",
    "Quinn",
    "Morgan",
    "Taylor",
    "Cameron",
    "Hayden",
    "Reese",
)
_LAST_NAMES = (
    "Smith",
    "Nguyen",
    "Patel",
    "Garcia",
    "Okafor",
    "Ivanov",
    "Chen",
    "Silva",
    "Berg",
    "Dubois",
)
_ORG_SUFFIXES = ("Labs", "Group", "Systems", "Partners", "Collective")
_STREETS = ("Maple", "Cedar", "Willow", "Harbor", "Summit", "River")
_CITIES = ("Exampleton", "Fictoria", "Sampleville", "Demoville")


class PseudonymRegistry:
    """Deterministic within one request; discarded when the request ends."""

    def __init__(self, seed: str = "") -> None:
        self._seed = seed
        self._map: dict[tuple[str, str], str] = {}
        self._used: set[str] = set()
        self._counters: dict[str, int] = {}

    def pseudonymize(self, entity_type: str, value: str) -> str:
        key = (entity_type, normalize_pseudonym_key(entity_type, value))
        existing = self._map.get(key)
        if existing is not None:
            return existing
        candidate = self._generate(entity_type, value)
        attempt = 0
        unique = candidate
        while unique in self._used:
            attempt += 1
            unique = f"{candidate}_{attempt}"
        self._used.add(unique)
        self._map[key] = unique
        return unique

    def _next_counter(self, kind: str) -> int:
        self._counters[kind] = self._counters.get(kind, 0) + 1
        return self._counters[kind]

    def _generate(self, entity_type: str, value: str) -> str:
        digest = hashlib.sha256(
            f"{self._seed}|{entity_type}|{normalize_pseudonym_key(entity_type, value)}".encode()
        ).hexdigest()
        bucket = int(digest[:8], 16)

        if entity_type == EntityType.PERSON:
            return (
                f"{_FIRST_NAMES[bucket % len(_FIRST_NAMES)]} "
                f"{_LAST_NAMES[(bucket // 10) % len(_LAST_NAMES)]}"
            )
        if entity_type == EntityType.EMAIL_ADDRESS:
            return f"user_{self._next_counter('email'):03d}@example.com"
        if entity_type == EntityType.PHONE_NUMBER:
            n = self._next_counter("phone")
            return f"902-555-{1000 + (n % 9000):04d}"
        if entity_type == EntityType.STREET_ADDRESS:
            n = self._next_counter("street")
            return f"{100 + n} {_STREETS[bucket % len(_STREETS)]} Street"
        if entity_type == EntityType.CANADIAN_POSTAL_CODE:
            letters = "ABCEGHJ"
            return (
                f"X{bucket % 10}{letters[bucket % len(letters)]} "
                f"{bucket % 10}{letters[(bucket // 3) % len(letters)]}{bucket % 10}"
            )
        if entity_type == EntityType.DATE_OF_BIRTH:
            return f"1990-{(bucket % 12) + 1:02d}-{(bucket % 28) + 1:02d}"
        if entity_type == EntityType.CREDIT_CARD:
            n = self._next_counter("card")
            return _luhn_complete(f"411111111111{(n % 1000):03d}")
        if entity_type == EntityType.CANADIAN_SIN:
            n = self._next_counter("sin")
            prefix = f"9{(n % 10_000_000):07d}"
            return make_valid_sin(prefix)
        if entity_type == EntityType.BANK_ACCOUNT:
            n = self._next_counter("bank")
            return (
                f"Transit: {(n % 90000) + 10000:05d} / "
                f"Institution: {(n % 900) + 100:03d} / Account: {1000000 + n}"
            )
        if entity_type == EntityType.IP_ADDRESS:
            n = self._next_counter("ip")
            return f"203.0.113.{(n % 200) + 1}"
        if entity_type == EntityType.URL:
            n = self._next_counter("url")
            return f"https://example.com/user/{n:03d}"
        if entity_type == EntityType.ORGANIZATION:
            return (
                f"{_LAST_NAMES[bucket % len(_LAST_NAMES)]} "
                f"{_ORG_SUFFIXES[(bucket // 7) % len(_ORG_SUFFIXES)]}"
            )
        if entity_type == EntityType.LOCATION:
            return _CITIES[bucket % len(_CITIES)]
        if entity_type == EntityType.MEDICAL_IDENTIFIER:
            return f"MRN-FIC-{self._next_counter('mrn'):05d}"
        if entity_type == EntityType.CUSTOM_IDENTIFIER:
            return f"ID-FIC-{self._next_counter('custom'):05d}"
        return f"PSEUDO_{entity_type}_{self._next_counter('generic'):03d}"


def normalize_pseudonym_key(entity_type: str, value: str) -> str:
    if entity_type in {
        EntityType.EMAIL_ADDRESS,
        EntityType.PERSON,
        EntityType.ORGANIZATION,
        EntityType.LOCATION,
        EntityType.URL,
    }:
        return value.strip().casefold()
    if entity_type in {
        EntityType.PHONE_NUMBER,
        EntityType.CREDIT_CARD,
        EntityType.CANADIAN_SIN,
        EntityType.BANK_ACCOUNT,
    }:
        return digits_only(value)
    if entity_type == EntityType.CANADIAN_POSTAL_CODE:
        return value.replace(" ", "").replace("-", "").upper()
    return value.strip()


def _luhn_complete(partial: str) -> str:
    for check in range(10):
        candidate = f"{partial}{check}"
        if luhn_valid(candidate):
            return candidate
    return f"{partial}0"
