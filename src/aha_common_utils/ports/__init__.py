"""Business-independent port contracts."""

from aha_common_utils.ports.cache_store import CacheStorePort
from aha_common_utils.ports.file_scan import FileScanPort, ScanResult
from aha_common_utils.ports.file_storage import FileStoragePort
from aha_common_utils.ports.llm_provider import EmbeddingProviderPort, LLMProviderPort
from aha_common_utils.ports.ocr_provider import OcrLayoutBlock, OcrPageResult, OcrProviderPort
from aha_common_utils.ports.task_queue import GenericTaskConfig, TaskContext, TaskEnvelope, TaskQueuePort
from aha_common_utils.ports.types import EmbeddingVector, JsonObject, LLMMessage

__all__ = [
    "CacheStorePort",
    "EmbeddingProviderPort",
    "EmbeddingVector",
    "FileScanPort",
    "FileStoragePort",
    "GenericTaskConfig",
    "JsonObject",
    "LLMMessage",
    "LLMProviderPort",
    "OcrLayoutBlock",
    "OcrPageResult",
    "OcrProviderPort",
    "ScanResult",
    "TaskContext",
    "TaskEnvelope",
    "TaskQueuePort",
]
