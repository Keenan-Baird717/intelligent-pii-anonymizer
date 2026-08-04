"""Regex recognizer tests with fictional fixtures only."""

from app.processing.detection.types import EntityType
from app.recognizers.checksums import make_valid_sin
from app.recognizers.regex_recognizers import run_regex_recognizers


def _types(text: str) -> set[str]:
    return {c.entity_type for c in run_regex_recognizers(text)}


def test_email_recognition_and_offsets() -> None:
    text = "Contact fictional.user@example.com today."
    entities = run_regex_recognizers(text)
    email = next(e for e in entities if e.entity_type == EntityType.EMAIL_ADDRESS)
    assert email.text == "fictional.user@example.com"
    assert text[email.start : email.end] == email.text


def test_canadian_postal_formats() -> None:
    assert EntityType.CANADIAN_POSTAL_CODE in _types("Mail to B3H 1Y2 please.")
    assert EntityType.CANADIAN_POSTAL_CODE in _types("Mail to B3H1Y2 please.")
    entity = next(
        e
        for e in run_regex_recognizers("Code B3H1Y2 end")
        if e.entity_type == EntityType.CANADIAN_POSTAL_CODE
    )
    assert entity.normalized_value == "B3H 1Y2"


def test_canadian_phone_formats() -> None:
    for sample in ("902-555-0182", "(902) 555-0182", "+1 902 555 0182"):
        assert EntityType.PHONE_NUMBER in _types(f"Call {sample} now.")


def test_phone_rejects_arbitrary_digits() -> None:
    entities = run_regex_recognizers("Order number 123456789012 is not a phone.")
    assert all(e.entity_type != EntityType.PHONE_NUMBER for e in entities)


def test_sin_valid_invalid_checksum() -> None:
    valid = make_valid_sin("94645428")
    formatted = f"{valid[:3]}-{valid[3:6]}-{valid[6:]}"
    valid_entity = next(
        e
        for e in run_regex_recognizers(f"SIN {formatted}")
        if e.entity_type == EntityType.CANADIAN_SIN
    )
    assert valid_entity.checksum_valid is True
    assert valid_entity.confidence >= 0.95

    invalid = next(
        e
        for e in run_regex_recognizers("SIN 123-456-789")
        if e.entity_type == EntityType.CANADIAN_SIN
    )
    assert invalid.checksum_valid is False
    assert invalid.confidence <= 0.35


def test_credit_card_luhn() -> None:
    valid = next(
        e
        for e in run_regex_recognizers("Card 4111-1111-1111-1111")
        if e.entity_type == EntityType.CREDIT_CARD
    )
    assert valid.checksum_valid is True
    invalid = next(
        e
        for e in run_regex_recognizers("Card 4111-1111-1111-1112")
        if e.entity_type == EntityType.CREDIT_CARD
    )
    assert invalid.checksum_valid is False


def test_ip_url_street_dob_medical_bank_custom() -> None:
    text = (
        "Visit https://example.com from 203.0.113.10. "
        "Lived at 123 Fiction Street. Born Jan 15, 1990. "
        "MRN: ABCDE12345. Transit: 12345 / Institution: 001 / Account: 1234567. "
        "Reference EMP-AB12CD."
    )
    types = _types(text)
    assert EntityType.URL in types
    assert EntityType.IP_ADDRESS in types
    assert EntityType.STREET_ADDRESS in types
    assert EntityType.DATE_OF_BIRTH in types
    assert EntityType.MEDICAL_IDENTIFIER in types
    assert EntityType.BANK_ACCOUNT in types
    assert EntityType.CUSTOM_IDENTIFIER in types
