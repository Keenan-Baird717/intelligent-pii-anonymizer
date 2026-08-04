"""Deterministic regex recognizers. Offsets map to the original text."""

from __future__ import annotations

import re
from collections.abc import Callable

from app.processing.detection.models import CandidateEntity
from app.processing.detection.types import DetectionSource, EntityType
from app.recognizers.checksums import (
    canadian_sin_checksum_valid,
    canadian_sin_structurally_valid,
    digits_only,
    luhn_valid,
)

# Canadian postal: A1A 1A1 — first letter excludes D,F,I,O,Q,U,W,Z; letters exclude D,F,I,O,Q,U
_POSTAL = re.compile(
    r"\b([ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z])[ -]?(\d[ABCEGHJ-NPRSTV-Z]\d)\b",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?([2-9]\d{2})\)?[\s.-]?)([2-9]\d{2})[\s.-]?(\d{4})(?!\d)"
)
_CREDIT_CARD = re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")
_SIN = re.compile(r"(?<!\d)(\d{3}[ -]?\d{3}[ -]?\d{3})(?!\d)")
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_URL = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)
_STREET = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.'\-]+(?:\s+[A-Za-z0-9.'\-]+){0,4}\s+"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|"
    r"Place|Pl|Terrace|Ter|Crescent|Cres)\b",
    re.IGNORECASE,
)
_DOB = re.compile(
    r"\b(?:(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}|"
    r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"\d{1,2},?\s+(?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_MEDICAL = re.compile(
    r"\b(?:MRN|Medical Record(?: Number)?|Health Card(?: Number)?|"
    r"PHN|Chart(?: Number)?)\s*[:#]?\s*([A-Z0-9-]{5,20})\b",
    re.IGNORECASE,
)
# Conservative Canadian bank pattern: transit (5) + institution (3) + account (7-12)
_BANK = re.compile(
    r"\b(?:Transit|Branch)\s*[:#]?\s*(\d{5})\s*[/,]?\s*"
    r"(?:Institution|Inst)\s*[:#]?\s*(\d{3})\s*[/,]?\s*"
    r"(?:Account|Acct)\s*[:#]?\s*(\d{7,12})\b",
    re.IGNORECASE,
)
_CUSTOM = re.compile(r"\b(?:EMP|CUST|ID)-[A-Z0-9]{4,12}\b")


def run_regex_recognizers(text: str) -> list[CandidateEntity]:
    candidates: list[CandidateEntity] = []
    candidates.extend(_find_email(text))
    candidates.extend(_find_postal(text))
    candidates.extend(_find_phone(text))
    candidates.extend(_find_credit_cards(text))
    candidates.extend(_find_sins(text))
    candidates.extend(_find_ip(text))
    candidates.extend(_find_url(text))
    candidates.extend(_find_street(text))
    candidates.extend(_find_dob(text))
    candidates.extend(_find_medical(text))
    candidates.extend(_find_bank(text))
    candidates.extend(_find_custom(text))
    return candidates


def _match(
    text: str,
    pattern: re.Pattern[str],
    entity_type: str,
    recognizer_name: str,
    confidence: float,
    explanation: str,
    normalize: Callable[[str], str | None] | None = None,
) -> list[CandidateEntity]:
    results: list[CandidateEntity] = []
    for match in pattern.finditer(text):
        value = match.group(0)
        results.append(
            CandidateEntity(
                entity_type=entity_type,
                start=match.start(),
                end=match.end(),
                text=value,
                confidence=confidence,
                detection_source=DetectionSource.REGEX,
                recognizer_name=recognizer_name,
                normalized_value=normalize(value) if normalize else None,
                explanation=explanation,
            )
        )
    return results


def _find_email(text: str) -> list[CandidateEntity]:
    return _match(
        text,
        _EMAIL,
        EntityType.EMAIL_ADDRESS,
        "regex_email",
        0.95,
        "Matched email pattern",
        lambda v: v.lower(),
    )


def _find_postal(text: str) -> list[CandidateEntity]:
    results: list[CandidateEntity] = []
    for match in _POSTAL.finditer(text):
        forward = match.group(1).upper()
        local = match.group(2).upper()
        results.append(
            CandidateEntity(
                entity_type=EntityType.CANADIAN_POSTAL_CODE,
                start=match.start(),
                end=match.end(),
                text=match.group(0),
                confidence=0.93,
                detection_source=DetectionSource.REGEX,
                recognizer_name="regex_canadian_postal_code",
                normalized_value=f"{forward} {local}",
                explanation="Matched Canadian postal-code structure",
            )
        )
    return results


def _find_phone(text: str) -> list[CandidateEntity]:
    results: list[CandidateEntity] = []
    for match in _PHONE.finditer(text):
        area, exchange, subscriber = match.group(1), match.group(2), match.group(3)
        results.append(
            CandidateEntity(
                entity_type=EntityType.PHONE_NUMBER,
                start=match.start(),
                end=match.end(),
                text=match.group(0),
                confidence=0.88,
                detection_source=DetectionSource.REGEX,
                recognizer_name="regex_canadian_phone",
                normalized_value=f"+1{area}{exchange}{subscriber}",
                explanation="Matched North American phone pattern with NANP constraints",
            )
        )
    return results


def _find_credit_cards(text: str) -> list[CandidateEntity]:
    results: list[CandidateEntity] = []
    for match in _CREDIT_CARD.finditer(text):
        raw = match.group(0)
        digits = digits_only(raw)
        if not (13 <= len(digits) <= 19):
            continue
        valid = luhn_valid(digits)
        results.append(
            CandidateEntity(
                entity_type=EntityType.CREDIT_CARD,
                start=match.start(),
                end=match.end(),
                text=raw,
                confidence=0.97 if valid else 0.25,
                detection_source=DetectionSource.REGEX_CHECKSUM if valid else DetectionSource.REGEX,
                recognizer_name="regex_credit_card_luhn",
                checksum_valid=valid,
                normalized_value=digits,
                explanation=(
                    "Credit-card candidate passed Luhn validation"
                    if valid
                    else "Credit-card candidate failed Luhn validation"
                ),
            )
        )
    return results


def _find_sins(text: str) -> list[CandidateEntity]:
    results: list[CandidateEntity] = []
    for match in _SIN.finditer(text):
        raw = match.group(0)
        digits = digits_only(raw)
        if len(digits) != 9:
            continue
        structural = canadian_sin_structurally_valid(digits)
        checksum = canadian_sin_checksum_valid(digits) if structural else False
        if not structural:
            explanation = "SIN candidate structurally invalid"
            confidence = 0.15
            source = DetectionSource.REGEX
        elif not checksum:
            explanation = "SIN candidate structurally valid but checksum invalid"
            confidence = 0.3
            source = DetectionSource.REGEX
        else:
            explanation = "SIN candidate passed Canadian checksum validation"
            confidence = 0.97
            source = DetectionSource.REGEX_CHECKSUM
        results.append(
            CandidateEntity(
                entity_type=EntityType.CANADIAN_SIN,
                start=match.start(),
                end=match.end(),
                text=raw,
                confidence=confidence,
                detection_source=source,
                recognizer_name="regex_canadian_sin",
                checksum_valid=checksum if structural else False,
                normalized_value=digits,
                explanation=explanation,
            )
        )
    return results


def _find_ip(text: str) -> list[CandidateEntity]:
    return _match(
        text,
        _IPV4,
        EntityType.IP_ADDRESS,
        "regex_ipv4",
        0.9,
        "Matched IPv4 address",
    )


def _find_url(text: str) -> list[CandidateEntity]:
    return _match(
        text,
        _URL,
        EntityType.URL,
        "regex_url",
        0.9,
        "Matched URL pattern",
    )


def _find_street(text: str) -> list[CandidateEntity]:
    return _match(
        text,
        _STREET,
        EntityType.STREET_ADDRESS,
        "regex_street_address",
        0.65,
        "Matched conservative street-address pattern; may miss unconventional formats",
    )


def _find_dob(text: str) -> list[CandidateEntity]:
    return _match(
        text,
        _DOB,
        EntityType.DATE_OF_BIRTH,
        "regex_date_of_birth",
        0.6,
        "Matched date-like pattern; not all dates are dates of birth",
    )


def _find_medical(text: str) -> list[CandidateEntity]:
    results: list[CandidateEntity] = []
    for match in _MEDICAL.finditer(text):
        results.append(
            CandidateEntity(
                entity_type=EntityType.MEDICAL_IDENTIFIER,
                start=match.start(1),
                end=match.end(1),
                text=match.group(1),
                confidence=0.7,
                detection_source=DetectionSource.REGEX,
                recognizer_name="regex_medical_identifier",
                normalized_value=match.group(1).upper(),
                explanation="Matched labeled medical-identifier pattern (conservative)",
            )
        )
    return results


def _find_bank(text: str) -> list[CandidateEntity]:
    results: list[CandidateEntity] = []
    for match in _BANK.finditer(text):
        transit, institution, account = match.group(1), match.group(2), match.group(3)
        results.append(
            CandidateEntity(
                entity_type=EntityType.BANK_ACCOUNT,
                start=match.start(),
                end=match.end(),
                text=match.group(0),
                confidence=0.72,
                detection_source=DetectionSource.REGEX,
                recognizer_name="regex_canadian_bank_pattern",
                normalized_value=f"{transit}-{institution}-{account}",
                explanation=(
                    "Matched labeled Canadian transit/institution/account pattern; "
                    "pattern matching does not establish that an account is real"
                ),
            )
        )
    return results


def _find_custom(text: str) -> list[CandidateEntity]:
    return _match(
        text,
        _CUSTOM,
        EntityType.CUSTOM_IDENTIFIER,
        "regex_custom_identifier",
        0.75,
        "Matched EMP/CUST/ID custom identifier pattern",
    )
