from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

AddToServer = Callable[[Any, Any], None]


@dataclass(frozen=True, slots=True)
class ServiceRegistration:
    """A servicer plus a function that installs it into a server object."""

    servicer: Any
    add_to_server: AddToServer | None = None


class ServiceRegistry:
    """Small runtime registry for service instances."""

    def __init__(self) -> None:
        self._services: list[ServiceRegistration] = []

    def register(
        self,
        servicer: Any,
        add_to_server: AddToServer | None = None,
        *,
        db_engine: Any = None,
        db_session_factory: Any = None,
    ) -> None:
        if hasattr(servicer, "set_db_engine") and db_engine is not None:
            servicer.set_db_engine(db_engine, db_session_factory)
        self._services.append(ServiceRegistration(servicer=servicer, add_to_server=add_to_server))

    def resolve_add_to_server(self, servicer: Any) -> AddToServer:
        """Resolve a server installer for a servicer.

        Subclasses can override this when installer lookup is project-specific.
        """
        raise ValueError(f"No add_to_server resolved for {servicer.__class__.__name__}")

    async def initialize_all(self) -> None:
        for registration in self._services:
            initialize = getattr(registration.servicer, "initialize", None)
            if initialize is None:
                continue
            result = initialize()
            if inspect.isawaitable(result):
                await result

    async def close_all(self) -> None:
        for registration in reversed(self._services):
            close = getattr(registration.servicer, "close", None)
            if close is None:
                continue
            result = close()
            if inspect.isawaitable(result):
                await result

    def register_all_to_server(self, server: Any) -> None:
        for registration in self._services:
            installer = registration.add_to_server
            if installer is None:
                installer = self.resolve_add_to_server(registration.servicer)
            installer(registration.servicer, server)
