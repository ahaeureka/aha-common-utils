"""Reusable fakes for common ports."""

from aha_common_utils.testing.fakes.cache_store import FakeCacheStore
from aha_common_utils.testing.fakes.file_storage import FakeFileStorage
from aha_common_utils.testing.fakes.http_fetch import FakeHttpFetchProvider, make_fetch_response
from aha_common_utils.testing.fakes.llm_provider import FakeEmbeddingProvider, FakeLLMProvider
from aha_common_utils.testing.fakes.task_queue import FakeTaskQueue

__all__ = [
    "FakeCacheStore",
    "FakeEmbeddingProvider",
    "FakeFileStorage",
    "FakeHttpFetchProvider",
    "FakeLLMProvider",
    "FakeTaskQueue",
    "make_fetch_response",
]
