"""Unit tests for checksum validators using fictional values only."""

from app.recognizers.checksums import (
    canadian_sin_checksum_valid,
    canadian_sin_structurally_valid,
    luhn_valid,
    make_valid_sin,
)


def test_luhn_accepts_fictional_test_card() -> None:
    # Public Visa test number designated for software testing.
    assert luhn_valid("4111111111111111") is True


def test_luhn_rejects_invalid_card() -> None:
    assert luhn_valid("4111111111111112") is False


def test_sin_structural_and_checksum_states() -> None:
    valid = make_valid_sin("94645428")
    assert canadian_sin_structurally_valid(valid) is True
    assert canadian_sin_checksum_valid(valid) is True

    assert canadian_sin_structurally_valid("046454286") is False
    assert canadian_sin_checksum_valid("123456789") is False
