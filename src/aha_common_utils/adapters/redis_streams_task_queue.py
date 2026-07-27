from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from aha_common_utils.ports.task_queue import TaskEnvelope, TaskQueuePort
from aha_common_utils.ports.types import JsonObject

logger = logging.getLogger(__name__)

EnvelopeToDict = Callable[[Any], JsonObject]
EnvelopeFromDict = Callable[[JsonObject], Any]
IncrementAttempt = Callable[[Any], Any]


class RedisStreamsTaskQueue(TaskQueuePort):
    """Redis Streams implementation of TaskQueuePort."""

    def __init__(
        self,
        *,
        redis: Any | None = None,
        url: str | None = None,
        stream: str = "tasks",
        group: str = "workers",
        consumer_prefix: str = "",
        max_stream_length: int = 100_000,
        idle_claim_ms: int = 300_000,
        envelope_to_dict: EnvelopeToDict | None = None,
        envelope_from_dict: EnvelopeFromDict | None = None,
        increment_attempt: IncrementAttempt | None = None,
    ) -> None:
        if redis is None:
            if url is None:
                raise ValueError("Either redis or url must be provided")
            redis = self._redis_from_url(url)
        self._redis = redis
        self._stream = stream
        self._group = group
        self._consumer_prefix = consumer_prefix
        self._max_stream_length = max_stream_length
        self._idle_claim_ms = idle_claim_ms
        self._envelope_to_dict = envelope_to_dict or _default_envelope_to_dict
        self._envelope_from_dict = envelope_from_dict or TaskEnvelope.from_dict
        self._increment_attempt = increment_attempt or _default_increment_attempt
        self._message_ids: dict[str, str] = {}
        self._pending_messages = self._message_ids

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        stream: str = "tasks",
        group: str = "workers",
        consumer_prefix: str = "",
        max_stream_length: int = 100_000,
        idle_claim_ms: int = 300_000,
        envelope_to_dict: EnvelopeToDict | None = None,
        envelope_from_dict: EnvelopeFromDict | None = None,
        increment_attempt: IncrementAttempt | None = None,
        **redis_kwargs: Any,
    ) -> RedisStreamsTaskQueue:
        """Build a Redis Streams queue from a Redis connection URL."""
        return cls(
            redis=cls._redis_from_url(url, **redis_kwargs),
            stream=stream,
            group=group,
            consumer_prefix=consumer_prefix,
            max_stream_length=max_stream_length,
            idle_claim_ms=idle_claim_ms,
            envelope_to_dict=envelope_to_dict,
            envelope_from_dict=envelope_from_dict,
            increment_attempt=increment_attempt,
        )

    @staticmethod
    def _redis_from_url(url: str, **redis_kwargs: Any) -> Any:
        """Build a Redis client from a connection URL."""
        import redis.asyncio as aioredis

        return aioredis.from_url(url, **redis_kwargs)

    async def submit(self, envelope: TaskEnvelope) -> None:
        await self._ensure_group()
        payload = json.dumps(self._envelope_to_dict(envelope)).encode()
        await self._redis.xadd(name=self._stream, fields={"payload": payload}, maxlen=self._max_stream_length)

    async def consume_one(self, consumer_id: str) -> TaskEnvelope | None:
        await self._ensure_group()
        try:
            messages = await self._redis.xreadgroup(
                groupname=self._group,
                consumername=f"{self._consumer_prefix}{consumer_id}",
                streams={self._stream: ">"},
                count=1,
                block=2000,
            )
        except Exception:
            return None
        return self._decode_first(messages)

    async def acknowledge(self, task_id: str) -> None:
        message_id = self._message_ids.pop(task_id, task_id)
        try:
            await self._redis.xack(self._stream, self._group, message_id)
        except Exception:
            pass

    async def claim_pending(self, consumer_id: str) -> list[TaskEnvelope]:
        await self._ensure_group()
        try:
            _cursor, claimed, _deleted = await self._redis.xautoclaim(
                name=self._stream,
                groupname=self._group,
                consumername=f"{self._consumer_prefix}{consumer_id}",
                min_idle_time=self._idle_claim_ms,
                start_id="0-0",
                count=10,
            )
        except Exception:
            return []
        envelopes: list[TaskEnvelope] = []
        for message_id, fields in claimed:
            envelope = self._decode_message(message_id, fields)
            if envelope is None:
                continue
            envelopes.append(self._increment_attempt(envelope))
        return envelopes

    async def claims_pending(self, consumer_id: str) -> list[TaskEnvelope]:
        """Backward-compatible alias for claim_pending()."""
        return await self.claim_pending(consumer_id)

    async def close(self) -> None:
        close = getattr(self._redis, "aclose", None)
        if close is not None:
            await close()

    async def _ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(name=self._stream, groupname=self._group, id="0", mkstream=True)
        except Exception:
            pass

    def _decode_first(self, messages: Any) -> TaskEnvelope | None:
        if not messages:
            return None
        _stream_name, stream_messages = messages[0]
        if not stream_messages:
            return None
        message_id, fields = stream_messages[0]
        return self._decode_message(message_id, fields)

    def _decode_message(self, message_id: Any, fields: Any) -> TaskEnvelope | None:
        payload = fields.get(b"payload") or fields.get("payload")
        if not payload:
            return None
        try:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            raw = json.loads(str(payload))
            if not isinstance(raw, dict):
                return None
            envelope = self._envelope_from_dict(raw)
        except Exception:
            logger.warning("Failed to parse TaskEnvelope from queue message", exc_info=True)
            return None
        self._message_ids[envelope.task_id] = message_id.decode("utf-8") if isinstance(message_id, bytes) else str(message_id)
        return envelope


def _default_envelope_to_dict(envelope: TaskEnvelope) -> JsonObject:
    return envelope.to_dict()


def _default_increment_attempt(envelope: TaskEnvelope) -> TaskEnvelope:
    return TaskEnvelope(
        version=envelope.version,
        task_id=envelope.task_id,
        context=envelope.context,
        config=envelope.config,
        attempt=envelope.attempt + 1,
        metadata=envelope.metadata,
    )
