#!/usr/bin/env python3
"""Generate fictional Phase 5 Playwright PDF fixtures (no real documents or PII)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from tests.helpers.fictional_files import make_image_only_pdf, make_pdf_with_text  # noqa: E402

OUT = ROOT / "samples" / "fictional"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    text_pdf = make_pdf_with_text(
        [
            "Contact Alice Example at fictional.user@example.com phone 902-555-0182 "
            "and enough filler words for extraction threshold"
        ]
    )
    (OUT / "phase5-text-memo.pdf").write_bytes(text_pdf)
    (OUT / "phase5-image-only.pdf").write_bytes(make_image_only_pdf())
    print(f"Wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
