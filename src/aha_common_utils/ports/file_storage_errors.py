from __future__ import annotations


class StorageError(Exception):
    """Base class for file-storage errors."""


class StorageNotFoundError(StorageError):
    """The file id does not exist."""


class StorageQuotaError(StorageError):
    """Storage quota has been exceeded."""


class StorageAccessError(StorageError):
    """Permission denied or feature disabled."""


class StorageUnavailableError(StorageError):
    """Storage service is unavailable or timed out."""


class StorageSecurityError(StorageError):
    """A scanner detected malicious content."""

    def __init__(self, threat_name: str) -> None:
        super().__init__(f"Security scan detected threat: {threat_name}")
        self.threat_name = threat_name


class StorageIntegrityError(StorageError):
    """Downloaded bytes failed an integrity check."""
