from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from aha_common_utils.adapters.local_file_storage import LocalFileStorageAdapter
from aha_common_utils.ports.file_storage_errors import StorageIntegrityError
from aha_common_utils.ports.types import StoredFileInfo
from aha_common_utils.testing.fakes.file_storage import FakeFileStorage


def test_stored_file_info_backward_compatible_default() -> None:
    """AC-1: content_sha256 defaults to empty, existing construction unaffected."""
    info = StoredFileInfo(file_id="f1", filename="a.txt", content_type="text/plain", size_bytes=5)
    assert info.content_sha256 == ""
    # frozen/slots preserved — assignment should fail
    with pytest.raises((AttributeError, TypeError)):
        info.content_sha256 = "x"  # type: ignore[misc]


def test_stored_file_info_accepts_sha256() -> None:
    info = StoredFileInfo(
        file_id="f1", filename="a.txt", content_type="text/plain", size_bytes=5, content_sha256="abc123"
    )
    assert info.content_sha256 == "abc123"


async def test_local_upload_persists_sha256_and_get_info_returns_it(tmp_path: Path) -> None:
    storage = LocalFileStorageAdapter(root_dir=tmp_path)
    content = b"hello integrity"
    expected = hashlib.sha256(content).hexdigest()
    file_id = await storage.upload_file(
        filename="hello.txt", content=content, content_type="text/plain", folder="uploads"
    )
    info = await storage.get_file_info(file_id)
    assert info.content_sha256 == expected
    # metadata.json persisted
    meta_files = list(tmp_path.rglob("metadata.json"))
    assert len(meta_files) == 1
    raw = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert raw["content_sha256"] == expected


async def test_local_download_verify_true_passes_and_false_writes(tmp_path: Path) -> None:
    storage = LocalFileStorageAdapter(root_dir=tmp_path)
    content = b"verify me"
    file_id = await storage.upload_file(
        filename="v.txt", content=content, content_type="text/plain", folder="uploads"
    )
    out_true = tmp_path / "out_true.bin"
    await storage.download_file_to_path(file_id=file_id, output_path=str(out_true), verify_integrity=True)
    assert out_true.read_bytes() == content
    out_false = tmp_path / "out_false.bin"
    await storage.download_file_to_path(file_id=file_id, output_path=str(out_false), verify_integrity=False)
    assert out_false.read_bytes() == content


async def test_local_tamper_detected_verify_true_raises(tmp_path: Path) -> None:
    storage = LocalFileStorageAdapter(root_dir=tmp_path)
    file_id = await storage.upload_file(
        filename="t.txt", content=b"original", content_type="text/plain", folder="uploads"
    )
    # tamper underlying storage
    content_path = next(tmp_path.rglob("content.bin"))
    content_path.write_bytes(b"tampered")
    out = tmp_path / "out.bin"
    with pytest.raises(StorageIntegrityError):
        await storage.download_file_to_path(file_id=file_id, output_path=str(out), verify_integrity=True)
    # verify_integrity=False should still write (tampered bytes) without raising
    await storage.download_file_to_path(file_id=file_id, output_path=str(out), verify_integrity=False)
    assert out.read_bytes() == b"tampered"


async def test_fake_upload_persists_sha256_and_get_info(tmp_path: Path) -> None:
    storage = FakeFileStorage()
    content = b"fake content"
    expected = hashlib.sha256(content).hexdigest()
    file_id = await storage.upload_file(
        filename="f.txt", content=content, content_type="text/plain", folder="uploads"
    )
    info = await storage.get_file_info(file_id)
    assert info.content_sha256 == expected


async def test_fake_download_verify_true_and_tamper(tmp_path: Path) -> None:
    storage = FakeFileStorage()
    file_id = await storage.upload_file(
        filename="f.txt", content=b"original", content_type="text/plain", folder="uploads"
    )
    out = tmp_path / "out.bin"
    await storage.download_file_to_path(file_id=file_id, output_path=str(out), verify_integrity=True)
    assert out.read_bytes() == b"original"
    # tamper in-memory bytes
    info, _ = storage.files[file_id]
    storage.files[file_id] = (info, b"tampered")
    with pytest.raises(StorageIntegrityError):
        await storage.download_file_to_path(file_id=file_id, output_path=str(out), verify_integrity=True)
    await storage.download_file_to_path(file_id=file_id, output_path=str(out), verify_integrity=False)
    assert out.read_bytes() == b"tampered"


async def test_round_trip_normal_not_false_positive(tmp_path: Path) -> None:
    # AC-5 normal path not mis-reported
    for storage in [LocalFileStorageAdapter(root_dir=tmp_path / "local"), FakeFileStorage()]:
        # Local needs separate path; Fake ignores tmp_path but still test download
        content = b"round trip ok"
        file_id = await storage.upload_file(
            filename="ok.txt", content=content, content_type="text/plain", folder="uploads"
        )
        out = tmp_path / f"out_{id(storage)}.bin"
        await storage.download_file_to_path(file_id=file_id, output_path=str(out), verify_integrity=True)
        assert out.read_bytes() == content
