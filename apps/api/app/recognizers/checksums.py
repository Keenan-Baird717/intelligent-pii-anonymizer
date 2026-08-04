"""Checksum and structural validators. Never log candidate values."""

from __future__ import annotations


def digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def luhn_valid(number: str) -> bool:
    """Return True when the digit string passes the Luhn checksum."""
    digits = [int(ch) for ch in digits_only(number)]
    if len(digits) < 2:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def canadian_sin_structurally_valid(number: str) -> bool:
    """Nine digits; leading 0/8 are historically unused for permanent SINs."""
    digits = digits_only(number)
    if len(digits) != 9:
        return False
    return digits[0] not in {"0", "8"}


def canadian_sin_checksum_valid(number: str) -> bool:
    """Canadian SIN uses the Luhn algorithm over nine digits."""
    digits = digits_only(number)
    if len(digits) != 9:
        return False
    return luhn_valid(digits)


def make_valid_sin(eight_digit_prefix: str) -> str:
    """Generate a checksum-valid fictional SIN for tests (never use real SINs)."""
    digits = digits_only(eight_digit_prefix)
    if len(digits) != 8:
        raise ValueError("Prefix must be eight digits.")
    for check in range(10):
        candidate = digits + str(check)
        if canadian_sin_checksum_valid(candidate):
            return candidate
    raise RuntimeError("Unable to generate valid SIN.")
