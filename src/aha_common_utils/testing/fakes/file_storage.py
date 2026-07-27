from __future__ import annotations

from pathlib import Path

from aha_common_utils.ports.file_scan import FileScanPort
from aha_common_utils.ports.file_storage import FileStoragePort
from aha_common_utils.ports.file_storage_errors import StorageNotFoundError, StorageSecurityError
from aha_common_utils.ports.types import JsonObject, StoredFileInfo
from aha_common_utils.scanners.always_clean import AlwaysCleanScanner
from aha_common_utils.testing.fakes._failure import FailureMixin


class FakeFileStorage(FailureMixin, FileStoragePort):
    def __init__(self, scanner: FileScanPort | None = None) -> None:
        super().__init__()
        self._counter = 0
        self.files: dict[str, tuple[StoredFileInfo, bytes]] = {}
        self._scanner = scanner if scanner is not None else AlwaysCleanScanner()

    def reset(self) -> None:
        self._counter = 0
        self.files.clear()
        self._next_failure = None

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
        self._raise_if_failed()
        scan_result = await self._scanner.scan(filename=filename, content=content, content_type=content_type)
        if scan_result.verdict == "INFECTED":
            raise StorageSecurityError(scan_result.threat_name or "unknown")
        self._counter += 1
        file_id = f"file-{self._counter}"
        info = StoredFileInfo(
            file_id=file_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            metadata={"folder": folder, "business_id": business_id, **dict(metadata or {})},
        )
        self.files[file_id] = (info, content)
        return file_id

    async def get_file_info(self, file_id: str) -> StoredFileInfo:
        self._raise_if_failed()
        if file_id not in self.files:
            raise StorageNotFoundError(file_id)
        return self.files[file_id][0]

    async def download_file_to_path(
        self,
        *,
        file_id: str,
        output_path: str,
        verify_integrity: bool = True,
    ) -> str:
        self._raise_if_failed()
        if file_id not in self.files:
            raise StorageNotFoundError(file_id)
        Path(output_path).write_bytes(self.files[file_id][1])
        return output_path

    async def delete_file(self, file_id: str) -> None:
        self._raise_if_failed()
        self.files.pop(file_id, None)

    async def close(self) -> None:
        return None
