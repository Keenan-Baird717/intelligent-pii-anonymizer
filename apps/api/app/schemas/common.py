"""Shared Pydantic helpers for Phase 8 schema hardening."""

from __future__ import annotations

import math
from typing import Annotated, Any

from pydantic import AfterValidator, Field, field_validator


def reject_non_finite(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Numeric value required.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("NaN and infinite values are not allowed.")
    return number


FiniteFloat = Annotated[float, AfterValidator(reject_non_finite)]
NonNegativeFiniteFloat = Annotated[
    float,
    AfterValidator(reject_non_finite),
    Field(ge=0),
]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]


def forbid_config() -> dict[str, Any]:
    return {"extra": "forbid"}


class FiniteRectMixin:
    """Mixin providing finite float validation for rectangle coordinates."""

    @field_validator("x0", "y0", "x1", "y1", mode="before")
    @classmethod
    def _finite_coords(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Boolean coordinates are not allowed.")
        if isinstance(value, int | float):
            return reject_non_finite(float(value))
        return value
