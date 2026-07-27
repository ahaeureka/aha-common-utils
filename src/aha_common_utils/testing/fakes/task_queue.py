from __future__ import annotations

from collections import deque

from aha_common_utils.ports.task_queue import TaskEnvelope, TaskQueuePort
from aha_common_utils.testing.fakes._failure import FailureMixin


class FakeTaskQueue(FailureMixin, TaskQueuePort):
    def __init__(self) -> None:
        super().__init__()
        self._ready: deque[TaskEnvelope] = deque()
        self._pending: dict[str, TaskEnvelope] = {}

    async def submit(self, envelope: TaskEnvelope) -> None:
        self._raise_if_failed()
        self._ready.append(envelope)

    async def consume_one(self, consumer_id: str) -> TaskEnvelope | None:
        self._raise_if_failed()
        if not self._ready:
            return None
        envelope = self._ready.popleft()
        self._pending[envelope.task_id] = envelope
        return envelope

    async def acknowledge(self, task_id: str) -> None:
        self._raise_if_failed()
        self._pending.pop(task_id, None)

    async def claim_pending(self, consumer_id: str) -> list[TaskEnvelope]:
        self._raise_if_failed()
        return list(self._pending.values())

    async def close(self) -> None:
        return None
