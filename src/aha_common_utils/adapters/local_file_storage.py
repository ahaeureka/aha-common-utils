from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path

from aha_common_utils.ports.file_scan import FileScanPort
from aha_common_utils.ports.file_storage import FileStoragePort
from aha_common_utils.ports.file_storage_errors import StorageNotFoundError, StorageSecurityError
from aha_common_utils.ports.types import JsonObject, StoredFileInfo


class LocalFileStorageAdapter(FileStoragePort):
    """Filesystem-backed FileStoragePort for local development and tests."""

    def __init__(self, root_dir: Path | str, scanner: FileScanPort | None = None) -> None:
        self._root_dir = Path(root_dir)
        self._scanner = scanner

    async def upload_file(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str,
        folder: str,
        business_id: str | None = None,
        metadata: JsonObject | None = None,
    ) -> str:
        if self._scanner is not None:
            result = await self._scanner.scan(filename=filename, content=content, content_type=content_type)
            if result.verdict == "INFECTED":
                raise StorageSecurityError(result.threat_name or "unknown")
        file_id = str(uuid.uuid4())
        directory = self._root_dir / _safe_path_part(folder) / file_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "content.bin").write_bytes(content)
        info = StoredFileInfo(
            file_id=file_id,
            filename=Path(filename).name,
            content_type=content_type,
            size_bytes=len(content),
            metadata={"folder": folder, "business_id": business_id, **dict(metadata or {})},
        )
        (directory / "metadata.json").write_text(json.dumps(asdict(info)), encoding="utf-8")
        return file_id

    async def get_file_info(self, file_id: str) -> StoredFileInfo:
        metadata_path = self._find_metadata(file_id)
        if metadata_path is None:
            raise StorageNotFoundError(file_id)
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        return StoredFileInfo(**raw)

    async def download_file_to_path(
        self,
        *,
        file_id: str,
        output_path: str,
        verify_integrity: bool = True,
    ) -> str:
        metadata_path = self._find_metadata(file_id)
        if metadata_path is None:
            raise StorageNotFoundError(file_id)
        content_path = metadata_path.parent / "content.bin"
        Path(output_path).write_bytes(content_path.read_bytes())
        return output_path

    async def delete_file(self, file_id: str) -> None:
        metadata_path = self._find_metadata(file_id)
        if metadata_path is None:
            return
        for child in metadata_path.parent.iterdir():
            child.unlink()
        metadata_path.parent.rmdir()

    async def close(self) -> None:
        return None

    def _find_metadata(self, file_id: str) -> Path | None:
        for path in self._root_dir.glob(f"*/{file_id}/metadata.json"):
            return path
        return None


def _safe_path_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value.strip())
    return cleaned or "default"
