"""Entity-aware masking rules. Never log masked or original values."""

from __future__ import annotations

import re

from app.processing.detection.types import EntityType
from app.recognizers.checksums import digits_only


def mask_entity(entity_type: str, value: str) -> str:
    if entity_type == EntityType.EMAIL_ADDRESS:
        return _mask_email(value)
    if entity_type == EntityType.PHONE_NUMBER:
        return _mask_phone(value)
    if entity_type == EntityType.CREDIT_CARD:
        return _mask_credit_card(value)
    if entity_type == EntityType.CANADIAN_SIN:
        return _mask_sin(value)
    if entity_type == EntityType.CANADIAN_POSTAL_CODE:
        return _mask_postal(value)
    if entity_type == EntityType.IP_ADDRESS:
        return _mask_ip(value)
    if entity_type == EntityType.URL:
        return _mask_url(value)
    if entity_type in {EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION}:
        return _mask_name_like(value)
    if entity_type in {
        EntityType.BANK_ACCOUNT,
        EntityType.MEDICAL_IDENTIFIER,
        EntityType.CUSTOM_IDENTIFIER,
        EntityType.STREET_ADDRESS,
        EntityType.DATE_OF_BIRTH,
    }:
        return _mask_conservative(value)
    return _mask_conservative(value)


def _mask_email(value: str) -> str:
    if "@" not in value:
        return _mask_conservative(value)
    local, _, domain = value.partition("@")
    if not local:
        return f"*@{domain}"
    if len(local) == 1:
        return f"*@{domain}"
    return f"{local[0]}{'*' * max(len(local) - 1, 1)}@{domain}"


def _mask_phone(value: str) -> str:
    digits = digits_only(value)
    if len(digits) < 4:
        return "*" * len(value)
    last4 = digits[-4:]
    # Preserve separators shape where possible for common patterns.
    if re.fullmatch(r"\d{3}-\d{3}-\d{4}", value):
        return f"***-***-{last4}"
    if re.fullmatch(r"\(\d{3}\)\s*\d{3}-\d{4}", value):
        return f"(***) ***-{last4}"
    return f"{'*' * (len(digits) - 4)}{last4}"


def _mask_credit_card(value: str) -> str:
    digits = digits_only(value)
    if len(digits) < 4:
        return "*" * len(value)
    last4 = digits[-4:]
    if "-" in value:
        return f"****-****-****-{last4}"
    if " " in value:
        return f"**** **** **** {last4}"
    return f"{'*' * (len(digits) - 4)}{last4}"


def _mask_sin(value: str) -> str:
    digits = digits_only(value)
    if len(digits) < 3:
        return "*" * len(value)
    last3 = digits[-3:]
    if "-" in value:
        return f"***-***-{last3}"
    return f"{'*' * (len(digits) - 3)}{last3}"


def _mask_postal(value: str) -> str:
    compact = re.sub(r"\s+", "", value.upper())
    if len(compact) < 3:
        return "***"
    # Keep last three characters of the FSA+LDU compact form (e.g. 1Y2).
    return f"*** **{compact[-2:]}" if " " in value else f"***{compact[-2:]}"


def _mask_ip(value: str) -> str:
    parts = value.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.***.***.***"
    return _mask_conservative(value)


def _mask_url(value: str) -> str:
    # Keep scheme + host only when present; drop path/query.
    match = re.match(r"^(https?://[^/\s]+)", value, re.IGNORECASE)
    if match:
        return f"{match.group(1)}/*** "
    if value.lower().startswith("www."):
        host = value.split("/")[0]
        return f"{host}/***"
    return _mask_conservative(value)


def _mask_name_like(value: str) -> str:
    parts = value.split()
    if not parts:
        return "***"
    masked = []
    for part in parts:
        if len(part) <= 1:
            masked.append("*")
        else:
            masked.append(f"{part[0]}{'*' * (len(part) - 1)}")
    return " ".join(masked)


def _mask_conservative(value: str) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    if len(value) <= 4:
        return f"{value[0]}{'*' * (len(value) - 1)}"
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"
