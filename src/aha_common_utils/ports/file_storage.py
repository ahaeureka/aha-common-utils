from __future__ import annotations

from abc import ABC, abstractmethod

from aha_common_utils.ports.types import JsonObject, StoredFileInfo


class FileStoragePort(ABC):
    """File storage contract for raw files and generated artifacts."""

    @abstractmethod
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
        """Upload file bytes and return a file id."""

    @abstractmethod
    async def get_file_info(self, file_id: str) -> StoredFileInfo:
        """Read stored file metadata."""

    @abstractmethod
    async def download_file_to_path(
        self,
        *,
        file_id: str,
        output_path: str,
        verify_integrity: bool = True,
    ) -> str:
        """Download a file to a local path."""

    @abstractmethod
    async def delete_file(self, file_id: str) -> None:
        """Delete a stored file."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""
