from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DetectedKind(str, Enum):
    pdf = "pdf"
    png = "png"
    jpeg = "jpeg"
    pe = "pe"
    elf = "elf"
    zip = "zip"
    rar = "rar"
    seven_z = "seven_z"
    gzip = "gzip"
    empty = "empty"
    unknown = "unknown"


@dataclass(frozen=True)
class SignatureResult:
    kind: DetectedKind
    matched_bytes: int


EXECUTABLE_OR_ARCHIVE = {
    DetectedKind.pe,
    DetectedKind.elf,
    DetectedKind.zip,
    DetectedKind.rar,
    DetectedKind.seven_z,
    DetectedKind.gzip,
}


def detect_signature(header: bytes) -> SignatureResult:
    if not header:
        return SignatureResult(DetectedKind.empty, 0)

    if header.startswith(b"%PDF"):
        return SignatureResult(DetectedKind.pdf, 4)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return SignatureResult(DetectedKind.png, 8)
    if header.startswith(b"\xff\xd8\xff"):
        return SignatureResult(DetectedKind.jpeg, 3)
    if header.startswith(b"MZ"):
        return SignatureResult(DetectedKind.pe, 2)
    if header.startswith(b"\x7fELF"):
        return SignatureResult(DetectedKind.elf, 4)
    if (
        header.startswith(b"PK\x03\x04")
        or header.startswith(b"PK\x05\x06")
        or header.startswith(b"PK\x07\x08")
    ):
        return SignatureResult(DetectedKind.zip, 4)
    if header.startswith(b"Rar!\x1a\x07\x00") or header.startswith(b"Rar!\x1a\x07\x01\x00"):
        return SignatureResult(DetectedKind.rar, 7)
    if header.startswith(b"7z\xbc\xaf\x27\x1c"):
        return SignatureResult(DetectedKind.seven_z, 6)
    if header.startswith(b"\x1f\x8b"):
        return SignatureResult(DetectedKind.gzip, 2)
    return SignatureResult(DetectedKind.unknown, 0)
