from __future__ import annotations

import json
from typing import Any

from app.core.errors import AppError
from app.processing.pdf.types import BBox, MappedRectangle


def rectangles_to_json(
    rectangles: list[MappedRectangle] | list[BBox], *, page_number: int | None = None
) -> str:
    """Serialize rectangles for DB storage. Accepts MappedRectangle or plain BBox lists."""
    payload: list[dict[str, float]] = []
    for item in rectangles:
        if isinstance(item, MappedRectangle):
            payload.append(item.bbox.to_dict())
        else:
            payload.append(item.to_dict())
    _ = page_number  # page is stored separately on the entity
    return json.dumps(payload, separators=(",", ":"))


def rectangles_from_json(raw: str) -> list[BBox]:
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="ENTITY_MAPPING_FAILED",
            message="Entity rectangles are invalid.",
            status_code=400,
        ) from exc
    if not isinstance(data, list) or not data:
        raise AppError(
            code="ENTITY_MAPPING_FAILED",
            message="Entity rectangles are invalid.",
            status_code=400,
        )
    result: list[BBox] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise AppError(
                code="ENTITY_MAPPING_FAILED",
                message="Entity rectangles are invalid.",
                status_code=400,
            )
        try:
            bbox = BBox.from_dict(entry)
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError(
                code="ENTITY_MAPPING_FAILED",
                message="Entity rectangles are invalid.",
                status_code=400,
            ) from exc
        if bbox.x1 <= bbox.x0 or bbox.y1 <= bbox.y0:
            raise AppError(
                code="ENTITY_MAPPING_FAILED",
                message="Entity rectangles are invalid.",
                status_code=400,
            )
        result.append(bbox)
    return result


def validate_rectangle_dict(data: dict[str, float]) -> BBox:
    try:
        bbox = BBox(
            x0=float(data["x0"]),
            y0=float(data["y0"]),
            x1=float(data["x1"]),
            y1=float(data["y1"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(
            code="INVALID_RECTANGLE",
            message="Rectangle coordinates are invalid.",
            status_code=400,
        ) from exc
    if bbox.x1 <= bbox.x0 or bbox.y1 <= bbox.y0:
        raise AppError(
            code="INVALID_RECTANGLE",
            message="Rectangle coordinates are invalid.",
            status_code=400,
        )
    return bbox
