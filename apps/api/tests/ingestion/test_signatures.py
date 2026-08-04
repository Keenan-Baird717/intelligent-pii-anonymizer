from app.services.ingestion.signatures import DetectedKind, detect_signature
from tests.helpers.fictional_files import (
    elf_header_bytes,
    gzip_header_bytes,
    make_fictional_jpeg_bytes,
    make_fictional_pdf_bytes,
    make_fictional_png_bytes,
    pe_header_bytes,
    rar_header_bytes,
    seven_z_header_bytes,
    zip_header_bytes,
)


def test_detect_pdf_signature() -> None:
    header = make_fictional_pdf_bytes()[:64]
    result = detect_signature(header)
    assert result.kind is DetectedKind.pdf
    assert result.matched_bytes == 4


def test_detect_png_signature() -> None:
    result = detect_signature(make_fictional_png_bytes()[:64])
    assert result.kind is DetectedKind.png
    assert result.matched_bytes == 8


def test_detect_jpeg_signature() -> None:
    result = detect_signature(make_fictional_jpeg_bytes()[:64])
    assert result.kind is DetectedKind.jpeg
    assert result.matched_bytes == 3


def test_detect_empty() -> None:
    result = detect_signature(b"")
    assert result.kind is DetectedKind.empty


def test_detect_pe() -> None:
    assert detect_signature(pe_header_bytes()).kind is DetectedKind.pe


def test_detect_elf() -> None:
    assert detect_signature(elf_header_bytes()).kind is DetectedKind.elf


def test_detect_zip() -> None:
    assert detect_signature(zip_header_bytes()).kind is DetectedKind.zip


def test_detect_rar() -> None:
    assert detect_signature(rar_header_bytes()).kind is DetectedKind.rar


def test_detect_seven_z() -> None:
    assert detect_signature(seven_z_header_bytes()).kind is DetectedKind.seven_z


def test_detect_gzip() -> None:
    assert detect_signature(gzip_header_bytes()).kind is DetectedKind.gzip


def test_detect_unknown() -> None:
    assert detect_signature(b"NOT_A_REAL_FORMAT").kind is DetectedKind.unknown
