from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aha_common_utils.adapters.local_file_storage import LocalFileStorageAdapter
from aha_common_utils.ports.file_scan import FileScanPort, ScanResult
from aha_common_utils.ports.file_storage_errors import StorageNotFoundError, StorageSecurityError
from aha_common_utils.ports.llm_provider import EmbeddingProviderPort, LLMProviderPort
from aha_common_utils.ports.ocr_provider import OcrPageResult, OcrProviderPort
from aha_common_utils.ports.task_queue import GenericTaskConfig, InvalidEnvelopeError, TaskContext, TaskEnvelope
from aha_common_utils.ports.types import LLMMessage
from aha_common_utils.runtime.lifecycle import LifecycleRegistry, close_once
from aha_common_utils.runtime.request_context import (
    BillableSpan,
    RequestContext,
    get_request_context,
    request_context,
)
from aha_common_utils.runtime.service_registry import ServiceRegistry
from aha_common_utils.testing.fakes.task_queue import FakeTaskQueue


class AsyncResource:
    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


async def test_close_once_closes_each_resource_once() -> None:
    resource = AsyncResource()
    seen: set[int] = set()

    await close_once(resource, seen)
    await close_once(resource, seen)

    assert resource.closed == 1


async def test_lifecycle_registry_initializes_and_closes_in_reverse_order() -> None:
    events: list[str] = []

    class Service:
        def __init__(self, name: str) -> None:
            self.name = name

        async def initialize(self) -> None:
            events.append(f"init:{self.name}")

        async def close(self) -> None:
            events.append(f"close:{self.name}")

    registry = LifecycleRegistry()
    registry.register(Service("a"))
    registry.register(Service("b"))

    await registry.initialize_all()
    await registry.close_all()

    assert events == ["init:a", "init:b", "close:b", "close:a"]


async def test_service_registry_injects_db_and_registers_to_server() -> None:
    events: list[str] = []

    class Servicer:
        def set_db_engine(self, engine: object, session_factory: object) -> None:
            events.append(f"db:{engine}:{session_factory}")

        async def initialize(self) -> None:
            events.append("init")

        async def close(self) -> None:
            events.append("close")

    def add_to_server(servicer: object, server: object) -> None:
        events.append(f"add:{servicer.__class__.__name__}:{server}")

    registry = ServiceRegistry()
    registry.register(Servicer(), add_to_server, db_engine="engine", db_session_factory="factory")

    await registry.initialize_all()
    registry.register_all_to_server("server")
    await registry.close_all()

    assert events == ["db:engine:factory", "init", "add:Servicer:server", "close"]


def test_service_registry_can_resolve_add_to_server_from_subclass() -> None:
    events: list[str] = []

    class Servicer:
        pass

    class ResolvingRegistry(ServiceRegistry):
        def resolve_add_to_server(self, servicer: object):
            events.append(f"resolve:{servicer.__class__.__name__}")

            def add_to_server(servicer: object, server: object) -> None:
                events.append(f"add:{servicer.__class__.__name__}:{server}")

            return add_to_server

    registry = ResolvingRegistry()
    registry.register(Servicer())
    registry.register_all_to_server("server")

    assert events == ["resolve:Servicer", "add:Servicer:server"]


def test_request_context_records_billable_spans() -> None:
    ctx = RequestContext(request_id="req-1", user_id="user-1", metadata={"tenant": "demo"})

    with request_context(ctx) as active:
        active.record_span(
            BillableSpan(
                service="llm",
                model="test-model",
                input_units=3,
                output_units=5,
                latency_ms=12.0,
                trace_id="trace-1",
            )
        )
        assert get_request_context() is ctx
        assert active.total_llm_input_tokens == 3
        assert active.total_llm_output_tokens == 5
        assert active.billable_spans_count == 1
        assert active.metadata == {"tenant": "demo"}

    assert get_request_context() is None


async def test_local_file_storage_round_trips_bytes(tmp_path: Path) -> None:
    storage = LocalFileStorageAdapter(root_dir=tmp_path)

    file_id = await storage.upload_file(
        filename="hello.txt",
        content=b"hello",
        content_type="text/plain",
        folder="uploads",
        metadata={"purpose": "test"},
    )

    info = await storage.get_file_info(file_id)
    output_path = tmp_path / "downloaded.txt"
    await storage.download_file_to_path(file_id=file_id, output_path=str(output_path))

    assert info.filename == "hello.txt"
    assert info.metadata["purpose"] == "test"
    assert output_path.read_bytes() == b"hello"


async def test_local_file_storage_raises_for_missing_file(tmp_path: Path) -> None:
    storage = LocalFileStorageAdapter(root_dir=tmp_path)

    with pytest.raises(StorageNotFoundError):
        await storage.get_file_info("missing")


async def test_fake_file_storage_scans_uploads_and_resets() -> None:
    from aha_common_utils.scanners import MimeTypeAllowlistScanner
    from aha_common_utils.testing.fakes.file_storage import FakeFileStorage

    storage = FakeFileStorage(scanner=MimeTypeAllowlistScanner(["application/pdf"]))

    with pytest.raises(StorageSecurityError, match="MIME type blocked"):
        await storage.upload_file(
            filename="bad.exe",
            content=b"MZ",
            content_type="application/x-msdownload",
            folder="uploads",
        )

    file_id = await storage.upload_file(
        filename="doc.pdf",
        content=b"%PDF",
        content_type="application/pdf",
        folder="uploads",
    )
    assert file_id == "file-1"

    storage.reset()

    assert storage.files == {}
    assert await storage.upload_file(
        filename="doc.pdf",
        content=b"%PDF",
        content_type="application/pdf",
        folder="uploads",
    ) == "file-1"


async def test_fake_failure_mixin_accepts_string_messages() -> None:
    from aha_common_utils.testing.fakes.cache_store import FakeCacheStore

    cache = FakeCacheStore()
    cache.fail_next("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await cache.get("k")


async def test_fake_failure_mixin_accepts_exception_instances() -> None:
    from aha_common_utils.testing.fakes.cache_store import FakeCacheStore

    cache = FakeCacheStore()
    cache.fail_next(ValueError("typed boom"))

    with pytest.raises(ValueError, match="typed boom"):
        await cache.get("k")


async def test_fake_embedding_provider_tracks_query_and_document_calls() -> None:
    from aha_common_utils.testing.fakes.llm_provider import FakeEmbeddingProvider

    provider = FakeEmbeddingProvider(vector=[0.1, 0.2])

    query = await provider.embed_query("what is cache", task_description="retrieval")
    documents = await provider.embed_documents(["doc-a", "doc-b"])
    legacy = await provider.embed(["doc-c"])

    assert query == [0.1, 0.2]
    assert documents == [[0.1, 0.2], [0.1, 0.2]]
    assert legacy == [[0.1, 0.2]]
    assert provider.queries == ["what is cache"]
    assert provider.query_task_descriptions == ["retrieval"]
    assert provider.texts == ["doc-a", "doc-b", "doc-c"]
    assert provider.document_batch_calls == 2


async def test_reusable_scanners_match_storage_scan_contract() -> None:
    from aha_common_utils.scanners import AlwaysCleanScanner, MimeTypeAllowlistScanner

    clean = await AlwaysCleanScanner().scan(filename="doc.pdf", content=b"%PDF", content_type="application/pdf")
    blocked = await MimeTypeAllowlistScanner(["application/pdf"]).scan(
        filename="script.exe",
        content=b"MZ",
        content_type="application/x-msdownload",
    )

    assert clean == ScanResult(verdict="CLEAN", scanner_name="always_clean")
    assert clean.provider == "always_clean"
    assert blocked.verdict == "INFECTED"
    assert blocked.scanner_name == "mime_allowlist"
    assert blocked.threat_name == "MIME type blocked: application/x-msdownload"
    assert blocked.detail == "Allowed types: application/pdf"
    assert blocked.details == blocked.detail


async def test_reusable_chain_scanner_continues_after_unscannable_layer() -> None:
    from aha_common_utils.scanners import AlwaysCleanScanner, ChainFileScanner, MimeTypeAllowlistScanner

    class FailingScanner(FileScanPort):
        async def scan(self, *, filename: str, content: bytes, content_type: str) -> ScanResult:
            raise ConnectionError("scanner unavailable")

    chain = ChainFileScanner(
        [
            MimeTypeAllowlistScanner(["text/plain"]),
            FailingScanner(),
            AlwaysCleanScanner(),
        ]
    )
    result = await chain.scan(filename="note.txt", content=b"ok", content_type="text/plain")

    assert result.verdict == "UNSCANNABLE"
    assert result.scanner_name == "FailingScanner"
    assert result.detail == "scanner unavailable"


def test_task_envelope_rejects_local_paths() -> None:
    with pytest.raises(InvalidEnvelopeError):
        GenericTaskConfig.from_dict({"subject_id": "doc-1", "input_path": "/tmp/raw.pdf"})


async def test_fake_task_queue_submits_consumes_and_acknowledges() -> None:
    queue = FakeTaskQueue()
    envelope = TaskEnvelope(
        version=1,
        task_id="task-1",
        context=TaskContext(request_id="req-1", task_id="task-1"),
        config=GenericTaskConfig(subject_id="doc-1"),
    )

    await queue.submit(envelope)
    consumed = await queue.consume_one("consumer-a")
    await queue.acknowledge("task-1")

    assert consumed == envelope
    assert await queue.consume_one("consumer-a") is None


def test_redis_streams_task_queue_builds_from_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from aha_common_utils.adapters.redis_streams_task_queue import RedisStreamsTaskQueue

    calls: list[dict[str, object]] = []

    def from_url(url: str, **kwargs: object) -> object:
        calls.append({"url": url, **kwargs})
        return "redis-client"

    redis_asyncio = SimpleNamespace(from_url=from_url)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(asyncio=redis_asyncio))
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio)

    queue = RedisStreamsTaskQueue.from_url(
        "redis://localhost:6379/0",
        stream="unit-stream",
        group="unit-group",
        decode_responses=False,
    )

    assert queue._redis == "redis-client"
    assert queue._stream == "unit-stream"
    assert queue._group == "unit-group"
    assert calls == [{"url": "redis://localhost:6379/0", "decode_responses": False}]


def test_cache_store_registry_creates_redis_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from aha_common_utils.cache.provider_registry import CacheStoreConfig, available_cache_stores, create_cache_store

    calls: list[str] = []

    def from_url(url: str) -> object:
        calls.append(url)
        return "redis-client"

    redis_asyncio = SimpleNamespace(from_url=from_url)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(asyncio=redis_asyncio))
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio)

    cache = create_cache_store(
        CacheStoreConfig(
            provider="redis-cache",
            url="redis://localhost:6379/0",
            key_prefix="unit",
        )
    )

    assert "redis-cache" in available_cache_stores()
    assert cache._client is None
    assert cache._key("item") == "unit:item"
    assert calls == []


async def test_redis_cache_adapter_lazily_connects_and_closes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from aha_common_utils.adapters.redis_cache import RedisCacheAdapter

    calls: list[str] = []

    class RedisClient:
        def __init__(self) -> None:
            self.closed = 0

        async def get(self, key: str) -> bytes:
            assert key == "unit:item"
            return b"value"

        async def aclose(self) -> None:
            self.closed += 1

    client = RedisClient()

    def from_url(url: str) -> RedisClient:
        calls.append(url)
        return client

    redis_asyncio = SimpleNamespace(from_url=from_url)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(asyncio=redis_asyncio))
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio)

    cache = RedisCacheAdapter(url="redis://localhost:6379/0", key_prefix="unit:")

    assert cache._client is None
    assert await cache.get("item") == b"value"
    await cache.close()
    await cache.close()

    assert calls == ["redis://localhost:6379/0"]
    assert client.closed == 1
    assert cache._client is None


async def test_redis_cache_adapter_rejects_empty_or_prefixed_keys() -> None:
    from aha_common_utils.adapters.redis_cache import RedisCacheAdapter

    cache = RedisCacheAdapter(url="redis://localhost:6379/0", key_prefix="unit:")

    with pytest.raises(ValueError, match="key must not be empty"):
        await cache.get("")
    with pytest.raises(ValueError, match="key already has prefix"):
        await cache.get("unit:item")


def test_task_queue_registry_creates_redis_streams_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    from aha_common_utils.task_queue.provider_registry import TaskQueueConfig, available_task_queues, create_task_queue

    calls: list[dict[str, object]] = []

    def from_url(url: str, **kwargs: object) -> object:
        calls.append({"url": url, **kwargs})
        return "redis-client"

    redis_asyncio = SimpleNamespace(from_url=from_url)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(asyncio=redis_asyncio))
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio)

    queue = create_task_queue(
        TaskQueueConfig(
            provider="redis-streams",
            url="redis://localhost:6379/0",
            stream="unit-stream",
            group="unit-group",
        )
    )

    assert "redis-streams" in available_task_queues()
    assert queue._redis == "redis-client"
    assert queue._stream == "unit-stream"
    assert queue._group == "unit-group"
    assert calls == [{"url": "redis://localhost:6379/0"}]


async def test_redis_streams_task_queue_uses_consumer_groups_and_recovers_pending() -> None:
    from aha_common_utils.adapters.redis_streams_task_queue import RedisStreamsTaskQueue

    envelope = TaskEnvelope(
        version=1,
        task_id="task-1",
        context=TaskContext(request_id="req-1", task_id="task-1"),
        config=GenericTaskConfig(subject_id="doc-1"),
        attempt=1,
    )
    payload = json.dumps(envelope.to_dict()).encode()
    redis = AsyncMock()
    redis.xgroup_create = AsyncMock(return_value=True)
    redis.xadd = AsyncMock(return_value=b"1-0")
    redis.xreadgroup = AsyncMock(return_value=[(b"tasks", [(b"1-0", {b"payload": payload})])])
    redis.xack = AsyncMock(return_value=1)
    redis.xautoclaim = AsyncMock(return_value=(b"0-0", [(b"1-0", {b"payload": payload})], []))
    redis.aclose = AsyncMock()
    queue = RedisStreamsTaskQueue(
        redis=redis,
        stream="unit-stream",
        group="unit-group",
        consumer_prefix="unit-worker-",
        max_stream_length=123,
    )

    await queue.submit(envelope)
    consumed = await queue.consume_one("a")
    await queue.acknowledge("task-1")
    pending = await queue.claim_pending("a")
    await queue.close()

    redis.xadd.assert_awaited_once_with(name="unit-stream", fields={"payload": payload}, maxlen=123)
    redis.xreadgroup.assert_awaited_once_with(
        groupname="unit-group",
        consumername="unit-worker-a",
        streams={"unit-stream": ">"},
        count=1,
        block=2000,
    )
    redis.xack.assert_awaited_once_with("unit-stream", "unit-group", "1-0")
    redis.xautoclaim.assert_awaited_once()
    assert consumed == envelope
    assert pending[0].attempt == 2


async def test_redis_streams_task_queue_returns_none_for_queue_errors_or_invalid_payload() -> None:
    from aha_common_utils.adapters.redis_streams_task_queue import RedisStreamsTaskQueue

    redis = AsyncMock()
    redis.xgroup_create = AsyncMock(return_value=True)
    redis.xreadgroup = AsyncMock(side_effect=ConnectionError("redis down"))

    assert await RedisStreamsTaskQueue(redis=redis).consume_one("a") is None

    redis.xreadgroup = AsyncMock(return_value=[(b"tasks", [(b"1-0", {b"payload": b"not-json"})])])
    assert await RedisStreamsTaskQueue(redis=redis).consume_one("a") is None


async def test_redis_streams_task_queue_supports_custom_envelope_codec() -> None:
    from aha_common_utils.adapters.redis_streams_task_queue import RedisStreamsTaskQueue

    class CustomEnvelope:
        def __init__(self, task_id: str, attempt: int = 1) -> None:
            self.task_id = task_id
            self.attempt = attempt

        def to_dict(self) -> dict[str, object]:
            return {"task_id": self.task_id, "attempt": self.attempt}

        @classmethod
        def from_dict(cls, data: dict[str, object]) -> CustomEnvelope:
            return cls(task_id=str(data["task_id"]), attempt=int(str(data.get("attempt", 1))))

    redis = AsyncMock()
    redis.xgroup_create = AsyncMock(return_value=True)
    redis.xadd = AsyncMock(return_value=b"1-0")
    redis.xreadgroup = AsyncMock(
        return_value=[(b"tasks", [(b"1-0", {b"payload": json.dumps({"task_id": "custom-1"}).encode()})])]
    )
    redis.xautoclaim = AsyncMock(
        return_value=(b"0-0", [(b"2-0", {b"payload": json.dumps({"task_id": "custom-2"}).encode()})], [])
    )

    queue = RedisStreamsTaskQueue(
        redis=redis,
        envelope_to_dict=lambda envelope: envelope.to_dict(),
        envelope_from_dict=CustomEnvelope.from_dict,
        increment_attempt=lambda envelope: CustomEnvelope(envelope.task_id, envelope.attempt + 1),
    )

    await queue.submit(CustomEnvelope("custom-submit"))
    consumed = await queue.consume_one("a")
    pending = await queue.claim_pending("a")

    assert isinstance(consumed, CustomEnvelope)
    assert consumed.task_id == "custom-1"
    assert pending[0].task_id == "custom-2"
    assert pending[0].attempt == 2


async def test_llm_provider_registry_registers_and_creates_provider() -> None:
    from aha_common_utils.llm.provider_registry import (
        LLMProviderConfig,
        available_llm_providers,
        create_llm_provider,
        register_llm_provider,
    )

    class DummyLLMProvider(LLMProviderPort):
        def __init__(self, *, base_url: str, api_key: str, model: str, request_timeout_seconds: float = 60.0) -> None:
            self.base_url = base_url
            self.api_key = api_key
            self.model = model
            self.request_timeout_seconds = request_timeout_seconds

        async def complete_json(
            self,
            *,
            messages: list[LLMMessage],
            schema: type[object] | None = None,
            temperature: float = 0.0,
            max_tokens: int | None = None,
        ) -> dict[str, object]:
            return {"model": self.model, "messages": len(messages)}

        async def chat(
            self,
            *,
            messages: list[LLMMessage],
            temperature: float = 0.0,
            max_tokens: int | None = None,
        ) -> str:
            return "dummy"

        async def stream_text(
            self,
            *,
            messages: list[LLMMessage],
            temperature: float = 0.0,
            max_tokens: int | None = None,
        ) -> AsyncIterator[str]:
            yield "dummy"
            raise StopAsyncIteration

        async def stream_events(
            self,
            *,
            messages: list[LLMMessage],
            temperature: float = 0.0,
            max_tokens: int | None = None,
        ) -> AsyncIterator[dict[str, object]]:
            yield {"event": "dummy"}
            raise StopAsyncIteration

        async def close(self) -> None:
            return None

    register_llm_provider("unit-dummy-llm", DummyLLMProvider)

    provider = create_llm_provider(
        LLMProviderConfig(
            provider="unit-dummy-llm",
            base_url="https://llm.example.test",
            api_key="secret",
            model="model-a",
            request_timeout_seconds=12.0,
        )
    )

    assert "unit-dummy-llm" in available_llm_providers()
    assert isinstance(provider, DummyLLMProvider)
    assert provider.base_url == "https://llm.example.test"
    assert provider.model == "model-a"
    assert provider.request_timeout_seconds == 12.0


async def test_embedding_provider_registry_registers_and_creates_provider() -> None:
    from aha_common_utils.llm.provider_registry import (
        EmbeddingProviderConfig,
        available_embedding_providers,
        create_embedding_provider,
        register_embedding_provider,
    )

    class DummyEmbeddingProvider(EmbeddingProviderPort):
        def __init__(self, *, base_url: str, api_key: str, model: str, request_timeout_seconds: float = 60.0) -> None:
            self.base_url = base_url
            self.api_key = api_key
            self.model = model
            self.request_timeout_seconds = request_timeout_seconds

        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[float(index)] for index, _ in enumerate(texts)]

        async def close(self) -> None:
            return None

    register_embedding_provider("unit-dummy-embedding", DummyEmbeddingProvider)

    provider = create_embedding_provider(
        EmbeddingProviderConfig(
            provider="unit-dummy-embedding",
            base_url="https://embedding.example.test",
            api_key="secret",
            model="embedding-a",
            request_timeout_seconds=9.0,
        )
    )

    assert "unit-dummy-embedding" in available_embedding_providers()
    assert isinstance(provider, DummyEmbeddingProvider)
    assert provider.base_url == "https://embedding.example.test"
    assert provider.model == "embedding-a"
    assert provider.request_timeout_seconds == 9.0
    assert await provider.embed(["a", "b"]) == [[0.0], [1.0]]


def test_typed_provider_registry_helpers_create_and_list_instances() -> None:
    from aha_common_utils.runtime.provider_registry import (
        UnknownProviderError,
        available_provider_names,
        create_provider_instance,
        register_provider_class,
    )

    class BaseProvider:
        pass

    class DemoProvider(BaseProvider):
        def __init__(self, *, label: str, count: int = 1) -> None:
            self.label = label
            self.count = count

    register_provider_class("unit-demo-provider", DemoProvider)

    provider = create_provider_instance(
        "unit-demo-provider",
        BaseProvider,
        parameters={"label": "demo"},
        count=3,
    )

    assert isinstance(provider, DemoProvider)
    assert provider.label == "demo"
    assert provider.count == 3
    assert "unit-demo-provider" in available_provider_names(BaseProvider)

    with pytest.raises(UnknownProviderError, match="unknown provider: missing-provider"):
        create_provider_instance("missing-provider", BaseProvider)


class _FakeChatModel:
    """Minimal LangChain-compatible fake for testing OpenAICompatibleLLMProvider."""

    def __init__(self, response_content: str = "{\"answer\": 42}") -> None:
        self.response_content = response_content
        self.ainvoke_calls: list[object] = []
        self.ainvoke_configs: list[object] = []
        self.astream_chunks: list[object] = []
        self.astream_configs: list[object] = []
        self.astream_events_chunks: list[dict[str, object]] = []
        self.astream_events_configs: list[object] = []
        self.astream_events_versions: list[str] = []
        self.bind_kwargs: list[dict[str, object]] = []
        self._structured_schema: object = None
        self._structured_runnable: _FakeStructuredRunnable | None = None

    async def ainvoke(self, messages: object, config: object = None) -> object:
        self.ainvoke_calls.append(messages)
        self.ainvoke_configs.append(config)

        class _FakeMessage:
            content: str

        msg = _FakeMessage()
        msg.content = self.response_content
        return msg

    async def astream(self, messages: object, config: object = None):
        self.astream_configs.append(config)
        for chunk in self.astream_chunks:
            yield chunk

    async def astream_events(self, messages: object, version: str = "v2", config: object = None):
        self.astream_events_versions.append(version)
        self.astream_events_configs.append(config)
        for event in self.astream_events_chunks:
            yield event

    def bind(self, **kwargs: object) -> _FakeChatModel:
        self.bind_kwargs.append(kwargs)
        return self

    def with_structured_output(self, schema: object) -> object:
        self._structured_schema = schema
        self._structured_runnable = _FakeStructuredRunnable(self.response_content, schema)
        return self._structured_runnable


class _FakeStructuredRunnable:
    def __init__(self, response_content: str, schema: object) -> None:
        self.response_content = response_content
        self.schema = schema
        self.ainvoke_configs: list[object] = []
        self.bind_kwargs: list[dict[str, object]] = []

    async def ainvoke(self, messages: object, config: object = None) -> object:  # noqa: ARG002
        self.ainvoke_configs.append(config)
        import json

        if hasattr(self.schema, "model_validate"):
            model_validate = self.schema.model_validate
            return model_validate(json.loads(self.response_content))
        from aha_common_utils.llm.json_helpers import coerce_json_object

        return coerce_json_object(json.loads(self.response_content))

    def bind(self, **kwargs: object) -> _FakeStructuredRunnable:
        self.bind_kwargs.append(kwargs)
        return self


async def test_openai_compatible_llm_provider_parses_json_response() -> None:
    from aha_common_utils.adapters.openai_compatible_llm import OpenAICompatibleLLMProvider

    chat_model = _FakeChatModel(response_content="{\"answer\": 42}")
    provider = OpenAICompatibleLLMProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-token",
        model="json-model",
        chat_model=chat_model,
    )

    result = await provider.complete_json(
        messages=[LLMMessage(role="user", content="Return JSON")],
        temperature=0.25,
        max_tokens=128,
    )
    await provider.close()

    assert result == {"answer": 42}
    assert len(chat_model.ainvoke_calls) == 1
    assert chat_model.bind_kwargs == [{"temperature": 0.25, "max_tokens": 128}]
    assert chat_model.ainvoke_configs == [None]


async def test_openai_compatible_llm_provider_fenced_json_response() -> None:
    from aha_common_utils.adapters.openai_compatible_llm import OpenAICompatibleLLMProvider

    chat_model = _FakeChatModel(response_content="```json\n{\"answer\": 42}\n```")
    provider = OpenAICompatibleLLMProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-token",
        model="json-model",
        chat_model=chat_model,
    )

    result = await provider.complete_json(
        messages=[LLMMessage(role="user", content="Return JSON")],
    )
    assert result == {"answer": 42}


async def test_openai_compatible_llm_provider_structured_output() -> None:
    import json

    from aha_common_utils.adapters.openai_compatible_llm import OpenAICompatibleLLMProvider

    chat_model = _FakeChatModel(response_content=json.dumps({"name": "Alice", "score": 95}))
    provider = OpenAICompatibleLLMProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-token",
        model="json-model",
        chat_model=chat_model,
    )

    result = await provider.complete_json(
        messages=[LLMMessage(role="user", content="Extract")],
        schema=type("Person", (), {"__name__": "Person", "model_json_schema": classmethod(lambda cls: {  # type: ignore[arg-type]
            "type": "object", "properties": {"name": {"type": "string"}, "score": {"type": "integer"}}
        })}),
        temperature=0.4,
        max_tokens=64,
    )
    assert result == {"name": "Alice", "score": 95}
    assert chat_model._structured_runnable is not None
    assert chat_model._structured_runnable.bind_kwargs == [{"temperature": 0.4, "max_tokens": 64}]
    assert chat_model._structured_runnable.ainvoke_configs == [None]


async def test_openai_compatible_llm_provider_stream_text() -> None:
    from aha_common_utils.adapters.openai_compatible_llm import OpenAICompatibleLLMProvider

    chat_model = _FakeChatModel()
    chat_model.astream_chunks = [
        type("Chunk", (), {"content": "Hello"})(),
        type("Chunk", (), {"content": " World"})(),
    ]
    provider = OpenAICompatibleLLMProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-token",
        model="json-model",
        chat_model=chat_model,
    )

    chunks: list[str] = []
    async for chunk in provider.stream_text(
        messages=[LLMMessage(role="user", content="Hi")],
        temperature=0.6,
        max_tokens=32,
    ):
        chunks.append(chunk)

    assert chunks == ["Hello", " World"]
    assert chat_model.bind_kwargs == [{"temperature": 0.6, "max_tokens": 32}]
    assert chat_model.astream_configs == [None]


async def test_openai_compatible_llm_provider_stream_events() -> None:
    from aha_common_utils.adapters.openai_compatible_llm import OpenAICompatibleLLMProvider

    chat_model = _FakeChatModel()
    chat_model.astream_events_chunks = [
        {"event": "on_chat_model_start", "name": "ChatModel", "run_id": "r1", "parent_ids": [], "tags": [], "metadata": {}, "data": {}},
        {"event": "on_chat_model_stream", "name": "ChatModel", "run_id": "r1", "parent_ids": [], "tags": [], "metadata": {}, "data": {"chunk": "Hi"}},
    ]
    provider = OpenAICompatibleLLMProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-token",
        model="json-model",
        chat_model=chat_model,
    )

    events: list[dict[str, object]] = []
    async for event in provider.stream_events(
        messages=[LLMMessage(role="user", content="Hi")],
        temperature=0.8,
        max_tokens=16,
    ):
        events.append(event)

    assert len(events) == 2
    assert events[0]["event"] == "on_chat_model_start"
    assert events[0]["run_id"] == "r1"
    assert chat_model.bind_kwargs == [{"temperature": 0.8, "max_tokens": 16}]
    assert chat_model.astream_events_versions == ["v2"]
    assert chat_model.astream_events_configs == [None]


async def test_openai_compatible_llm_provider_chat_returns_raw_content() -> None:
    from aha_common_utils.adapters.openai_compatible_llm import OpenAICompatibleLLMProvider

    chat_model = _FakeChatModel(response_content="hello world")
    provider = OpenAICompatibleLLMProvider(
        base_url="https://llm.example.test/v1",
        api_key="secret-token",
        model="json-model",
        chat_model=chat_model,
    )

    result = await provider.chat(
        messages=[LLMMessage(role="user", content="Say hello")],
        temperature=0.3,
        max_tokens=64,
    )

    assert result == "hello world"
    assert chat_model.bind_kwargs == [{"temperature": 0.3, "max_tokens": 64}]


async def test_fake_llm_provider_chat_returns_configured_response() -> None:
    from aha_common_utils.testing.fakes.llm_provider import FakeLLMProvider

    provider = FakeLLMProvider(raw_responses=["raw-1"])

    assert await provider.chat(messages=[LLMMessage(role="user", content="Say hello")]) == "raw-1"


async def test_fake_llm_provider_stream_text_yields_configured_chunks() -> None:
    from aha_common_utils.testing.fakes.llm_provider import FakeLLMProvider

    provider = FakeLLMProvider(responses=[{"ok": True}])
    provider.set_text_chunks(["chunk-a", "chunk-b"])

    chunks: list[str] = []
    async for chunk in provider.stream_text(messages=[LLMMessage(role="user", content="Hi")]):
        chunks.append(chunk)

    assert chunks == ["chunk-a", "chunk-b"]
    assert len(provider.stream_text_calls) == 1


async def test_fake_llm_provider_stream_events_yields_configured_events() -> None:
    from aha_common_utils.testing.fakes.llm_provider import FakeLLMProvider

    provider = FakeLLMProvider()
    provider.set_event_chunks([
        {"event": "on_chat_model_stream", "name": "ChatModel", "run_id": "r1", "parent_ids": [], "tags": [], "metadata": {}, "data": {}},
        {"event": "on_chat_model_end", "name": "ChatModel", "run_id": "r1", "parent_ids": [], "tags": [], "metadata": {}, "data": {}},
    ])

    events: list[dict[str, object]] = []
    async for event in provider.stream_events(messages=[LLMMessage(role="user", content="Hi")]):
        events.append(event)

    assert len(events) == 2
    assert events[0]["event"] == "on_chat_model_stream"


def test_llm_json_helpers_parse_fenced_content_and_coerce_objects() -> None:
    from dataclasses import dataclass

    from aha_common_utils.llm.json_helpers import (
        coerce_json_object,
        extract_content,
        extract_json_block,
        extract_request_id_from_exception,
        parse_json_content,
    )
    from pydantic import BaseModel

    @dataclass
    class DataclassResponse:
        answer: int

    class PydanticResponse(BaseModel):
        answer: int

    class MessageResponse:
        content = "```json\n{\"answer\": 42}\n```"

    class ErrorResponse:
        text = "bad request"
        headers = {"x-request-id": "req-42"}

    class ApiError(Exception):
        response = ErrorResponse()

    assert extract_content({"content": "{\"answer\": 1}"}) == "{\"answer\": 1}"
    assert parse_json_content(MessageResponse()) == {"answer": 42}
    assert extract_json_block("prefix {\"answer\": 7} suffix") == {"answer": 7}
    assert coerce_json_object(DataclassResponse(answer=8)) == {"answer": 8}
    assert coerce_json_object(PydanticResponse(answer=9)) == {"answer": 9}
    assert extract_request_id_from_exception(ApiError()) == "req-42"


def test_json_value_helpers_flatten_numeric_lists() -> None:
    from aha_common_utils.json_values import flatten_numeric_list

    assert flatten_numeric_list([1, "2.5", [3, "bad", [4.25]], None]) == [1.0, 2.5, 3.0, 4.25]
    assert flatten_numeric_list({"not": "a-list"}) == []


async def test_storage_helpers_sanitize_and_enforce_scan_results() -> None:
    from aha_common_utils.ports.file_scan import ScanResult
    from aha_common_utils.storage.helpers import enforce_clean_scan, sanitize_metadata_key, sanitize_path_part

    class Scanner:
        def __init__(self, result: ScanResult) -> None:
            self.result = result

        async def scan(self, *, filename: str, content: bytes, content_type: str) -> ScanResult:
            return self.result

    assert sanitize_path_part(" /biz 1/a?.pdf ") == "biz-1/a-.pdf"
    assert sanitize_metadata_key("X Source!") == "x-source"

    await enforce_clean_scan(
        Scanner(ScanResult(verdict="CLEAN", scanner_name="unit")),
        filename="doc.pdf",
        content=b"%PDF",
        content_type="application/pdf",
        security_error_factory=RuntimeError,
    )

    with pytest.raises(RuntimeError, match="virus"):
        await enforce_clean_scan(
            Scanner(ScanResult(verdict="INFECTED", scanner_name="unit", threat_name="virus")),
            filename="bad.pdf",
            content=b"bad",
            content_type="application/pdf",
            security_error_factory=RuntimeError,
        )


class _FakeLangChainEmbeddings:
    """Minimal LangChain-compatible fake for testing OpenAICompatibleEmbeddingProvider."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.aembed_documents_calls: list[list[str]] = []
        self.closed = False

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.aembed_documents_calls.append(texts)
        return self.vectors

    async def close(self) -> None:
        self.closed = True


async def test_openai_compatible_embedding_provider_preserves_input_order() -> None:
    from aha_common_utils.adapters.openai_compatible_embedding import OpenAICompatibleEmbeddingProvider

    embedding_model = _FakeLangChainEmbeddings(vectors=[[1.0, 2.0], [3.0, 4.0]])
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://emb.example",
        api_key="secret",
        model="emb",
        embedding_model=embedding_model,
    )

    result = await provider.embed_texts(["first", "second"])
    await provider.close()

    assert result == [[1.0, 2.0], [3.0, 4.0]]
    assert embedding_model.closed is True


async def test_openai_compatible_embedding_provider_empty_input() -> None:
    from aha_common_utils.adapters.openai_compatible_embedding import OpenAICompatibleEmbeddingProvider

    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://emb.example",
        api_key="secret",
        model="emb",
        embedding_model=_FakeLangChainEmbeddings(vectors=[]),
    )

    assert await provider.embed_texts([]) == []
    assert await provider.embed([]) == []


async def test_openai_compatible_embedding_provider_embed_legacy() -> None:
    from aha_common_utils.adapters.openai_compatible_embedding import OpenAICompatibleEmbeddingProvider

    embedding_model = _FakeLangChainEmbeddings(vectors=[[0.1, 0.2]])
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://emb.example",
        api_key="secret",
        model="emb",
        embedding_model=embedding_model,
    )

    result = await provider.embed(["legacy-text"])
    assert result == [[0.1, 0.2]]


async def test_remote_ocr_client_posts_verbose_request_and_maps_blocks(tmp_path: Path) -> None:
    from aha_common_utils.adapters.remote_ocr import RemoteOcrClient

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self) -> dict[str, object]:
            return {
                "model": "PP-DocLayoutV3",
                "text": "hello",
                "markdown": "hello",
                "json": {
                    "width": 100,
                    "height": 200,
                    "parsing_res_list": [
                        {
                            "block_label": "text",
                            "block_content": "hello",
                            "block_id": "b1",
                            "block_order": 1,
                            "block_bbox": [1, "2", [3.5]],
                            "block_polygon_points": [0, 0, 10, 10],
                        }
                    ],
                },
                "usage": {"pages": 1},
            }

    class FakeHttpClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def post(self, url: str, *, data: dict[str, object], files: dict[str, object]) -> FakeResponse:
            self.calls.append({"url": url, "data": data, "files": files})
            return FakeResponse()

    image = tmp_path / "page.png"
    image.write_bytes(b"fake-image")
    http_client = FakeHttpClient()
    client = RemoteOcrClient(api_url="https://ocr.example.test/v1/ocr", http_client=http_client)

    result = await client.recognize_file(image, language="Chinese")

    assert result.model == "PP-DocLayoutV3"
    assert result.blocks[0].label == "text"
    assert result.blocks[0].bbox == [1.0, 2.0, 3.5]
    assert result.metadata["width"] == 100
    assert http_client.calls[0]["data"] == {"response_format": "verbose", "language": "Chinese"}


async def test_ocr_provider_registry_registers_and_creates_provider() -> None:
    from aha_common_utils.ocr.provider_registry import (
        OcrProviderConfig,
        available_ocr_providers,
        create_ocr_provider,
        register_ocr_provider,
    )

    class DummyOcrProvider(OcrProviderPort):
        def __init__(self, *, model: str = "dummy") -> None:
            self.model = model

        async def recognize_file(self, path: Path, *, language: str = "Chinese") -> OcrPageResult:
            return OcrPageResult(model=self.model, text=path.name, markdown=language)

    register_ocr_provider("unit-dummy-ocr", DummyOcrProvider)

    provider = create_ocr_provider(OcrProviderConfig(provider="unit-dummy-ocr", extra_params={"model": "ocr-a"}))

    assert "unit-dummy-ocr" in available_ocr_providers()
    assert isinstance(provider, DummyOcrProvider)
    assert (await provider.recognize_file(Path("page.png"))).model == "ocr-a"


async def test_fake_ocr_provider_records_calls(tmp_path: Path) -> None:
    from aha_common_utils.testing.fakes.ocr_provider import FakeOcrProvider

    image = tmp_path / "page.png"
    image.write_bytes(b"fake-image")
    provider = FakeOcrProvider(results=[OcrPageResult(model="fake", text="body", markdown="body")])

    result = await provider.recognize_file(image, language="English")

    assert result.text == "body"
    assert provider.calls == [(image, "English")]
