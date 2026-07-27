"""Provider capability and batch-scheduling DTOs.

Typed contracts for what a provider can do, how items form batches,
and how results/telemetry are reported.  Every batch-capable adapter
declares its capabilities via ``ProviderCapability`` so the scheduler
can select a safe execution mode without exception-based discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ExecutionMode(StrEnum):
    """Provider execution modes the scheduler may select."""

    ONLINE_MULTI_INPUT = "online_multi_input"
    SERVER_ASYNC_BATCH = "server_async_batch"
    BOUNDED_PARALLEL = "bounded_parallel"
    SINGLE_OVERSIZED = "single_oversized"


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    """Declared capability of a batch-capable provider adapter."""

    supported_modes: tuple[ExecutionMode, ...]
    max_items_per_batch: int = 0
    max_tokens_per_batch: int = 0
    max_input_length: int = 0
    supports_partial_results: bool = False
    supports_status_query: bool = False
    supports_cancellation: bool = False
    supports_idempotency: bool = False

    @property
    def can_online_multi_input(self) -> bool:
        return ExecutionMode.ONLINE_MULTI_INPUT in self.supported_modes

    @property
    def can_server_async_batch(self) -> bool:
        return ExecutionMode.SERVER_ASYNC_BATCH in self.supported_modes

    @property
    def can_bounded_parallel(self) -> bool:
        return ExecutionMode.BOUNDED_PARALLEL in self.supported_modes

    @property
    def can_single_oversized(self) -> bool:
        return ExecutionMode.SINGLE_OVERSIZED in self.supported_modes


@dataclass(frozen=True, slots=True)
class BatchCohortKey:
    """Full identity key for cohort formation.

    Two items belong to the same batch cohort only when ALL fields match.
    """

    provider: str
    model: str
    task_type: str
    prompt_hash: str
    schema_hash: str
    reasoning: str = ""
    locale: str = ""
    security_scope: str = ""
    retention_policy: str = ""

    def as_key(self) -> str:
        parts = (
            self.provider,
            self.model,
            self.task_type,
            self.prompt_hash,
            self.schema_hash,
            self.reasoning,
            self.locale,
            self.security_scope,
            self.retention_policy,
        )
        return "|".join(parts)


@dataclass(frozen=True, slots=True)
class BatchItem:
    """A single item submitted to the scheduler."""

    item_id: str
    custom_id: str
    cohort_key: BatchCohortKey
    text: str
    input_tokens: int
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BatchRequest:
    """A scheduled batch sent to one provider call."""

    request_id: str
    cohort_key: BatchCohortKey
    mode: ExecutionMode
    items: tuple[BatchItem, ...]
    total_tokens: int = 0


class BatchItemStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"
    CANCELLED = "cancelled"


@dataclass
class BatchItemResult:
    """Per-item result from a batch execution."""

    custom_id: str
    status: BatchItemStatus
    output: Any = None
    error_code: str = ""
    error_message: str = ""
    provider_requests: int = 1


@dataclass(frozen=True, slots=True)
class BatchTelemetry:
    """Honest Provider telemetry: logical vs actual requests."""

    logical_batch_count: int = 0
    actual_provider_requests: int = 0
    fallback_requests: int = 0
    total_items: int = 0
    succeeded_items: int = 0
    failed_items: int = 0
    total_tokens: int = 0
    total_latency_ms: int = 0
