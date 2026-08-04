from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services.ingestion.storage import (
    delete_stored_file,
    generate_storage_key,
    promote_quarantine,
    resolve_storage_path,
    write_stream_to_quarantine,
)


def test_generate_storage_key_randomized_and_extension() -> None:
    key_a = generate_storage_key(".pdf")
    key_b = generate_storage_key("pdf")
    assert key_a.endswith(".pdf")
    assert key_b.endswith(".pdf")
    assert key_a != key_b
    stem = key_a[: -len(".pdf")]
    assert len(stem) == 32
    assert all(c in "0123456789abcdef" for c in stem)


def test_resolve_storage_path_containment(temp_upload_dir: Path) -> None:
    key = generate_storage_key(".png")
    path = resolve_storage_path(key, root=temp_upload_dir)
    assert path.parent == temp_upload_dir.resolve()
    assert path.name == key


def test_resolve_storage_path_rejects_traversal(temp_upload_dir: Path) -> None:
    with pytest.raises(AppError) as exc:
        resolve_storage_path("../escape.pdf", root=temp_upload_dir)
    assert exc.value.code == "STORAGE_FAILURE"

    with pytest.raises(AppError) as exc2:
        resolve_storage_path("subdir/file.pdf", root=temp_upload_dir)
    assert exc2.value.code == "STORAGE_FAILURE"


def test_write_stream_and_promote(temp_upload_dir: Path) -> None:
    chunks = [b"hello ", b"world"]
    path, size, header = write_stream_to_quarantine(
        chunks,
        max_bytes=1024,
        chunk_size=1024,
        root=temp_upload_dir,
    )
    assert size == 11
    assert header.startswith(b"hello")
    assert path.exists()
    assert path.name.startswith(".quarantine-")

    key = generate_storage_key(".png")
    final = promote_quarantine(path, key, root=temp_upload_dir)
    assert final.exists()
    assert not path.exists()
    assert final.read_bytes() == b"hello world"


def test_write_stream_empty_rejected(temp_upload_dir: Path) -> None:
    with pytest.raises(AppError) as exc:
        write_stream_to_quarantine([], max_bytes=100, chunk_size=1024, root=temp_upload_dir)
    assert exc.value.code == "EMPTY_FILE"
    assert list(temp_upload_dir.iterdir()) == []


def test_write_stream_oversized_mid_stream(temp_upload_dir: Path) -> None:
    chunks = [b"a" * 50, b"b" * 60]

    with pytest.raises(AppError) as exc:
        write_stream_to_quarantine(chunks, max_bytes=100, chunk_size=1024, root=temp_upload_dir)
    assert exc.value.code == "FILE_TOO_LARGE"
    assert list(temp_upload_dir.iterdir()) == []


def test_delete_stored_file(temp_upload_dir: Path) -> None:
    key = generate_storage_key(".pdf")
    path = resolve_storage_path(key, root=temp_upload_dir)
    path.write_bytes(b"%PDF-fictional")
    delete_stored_file(key, root=temp_upload_dir)
    assert not path.exists()
