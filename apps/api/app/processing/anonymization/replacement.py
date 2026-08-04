"""Entity replacement strategy: replace spans with <ENTITY_TYPE> labels."""

from __future__ import annotations


def replace_entity(entity_type: str) -> str:
    return f"<{entity_type.upper()}>"
