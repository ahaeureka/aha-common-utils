from __future__ import annotations


class FailureMixin:
    """Small helper for fakes that need to fail exactly once."""

    def __init__(self) -> None:
        self._next_failure: Exception | str | None = None

    def fail_next(self, failure: Exception | str) -> None:
        self._next_failure = failure

    def _raise_if_failed(self) -> None:
        if self._next_failure is None:
            return
        failure = self._next_failure
        self._next_failure = None
        if isinstance(failure, str):
            raise RuntimeError(failure)
        raise failure
