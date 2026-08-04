"""Text redaction: irreversible block-character replacement.

Redaction length matches the source span length (in Unicode code points) so that
surrounding layout is roughly preserved. This is distinct from PDF coordinate redaction.
"""

from __future__ import annotations

BLOCK = "█"


def redact_entity(source_text: str) -> str:
    length = len(source_text)
    if length <= 0:
        return ""
    return BLOCK * length
