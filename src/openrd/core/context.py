from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from typing import Any


Handler = Callable[..., Any]


class Context:
    """DeepSeek-Harness-inspired micro-kernel: services, events, reversible effects."""

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}
        self._listeners: dict[str, list[Handler]] = defaultdict(list)
        self._cleanups: list[Callable[[], None]] = []
        self._plugins: dict[str, Any] = {}
        self.project_id: str | None = None
        self.extras: dict[str, Any] = {}

    def provide(self, name: str, service: Any) -> None:
        previous = self._services.get(name)
        self._services[name] = service

        def cleanup() -> None:
            if previous is None:
                self._services.pop(name, None)
            else:
                self._services[name] = previous

        self._cleanups.append(cleanup)

    def require(self, name: str) -> Any:
        if name not in self._services:
            raise KeyError(f"service '{name}' is not registered")
        return self._services[name]

    def get(self, name: str, default: Any = None) -> Any:
        return self._services.get(name, default)

    def has(self, name: str) -> bool:
        return name in self._services

    def on(self, event: str, handler: Handler) -> None:
        self._listeners[event].append(handler)

        def cleanup() -> None:
            listeners = self._listeners.get(event, [])
            if handler in listeners:
                listeners.remove(handler)

        self._cleanups.append(cleanup)

    def effect(self, cleanup: Callable[[], None]) -> None:
        self._cleanups.append(cleanup)

    async def emit(self, event: str, payload: dict[str, Any] | None = None) -> list[Any]:
        data = payload or {}
        results: list[Any] = []
        for handler in list(self._listeners.get(event, [])):
            result = handler(data)
            if inspect.isawaitable(result):
                result = await result
            results.append(result)
        wildcard = list(self._listeners.get("*", []))
        for handler in wildcard:
            result = handler(event, data)
            if inspect.isawaitable(result):
                result = await result
            results.append(result)
        return results

    def emit_sync(self, event: str, payload: dict[str, Any] | None = None) -> None:
        data = payload or {}
        for handler in list(self._listeners.get(event, [])):
            result = handler(data)
            if inspect.isawaitable(result):
                raise RuntimeError(f"async handler for '{event}' called via emit_sync")

    def unload(self) -> None:
        while self._cleanups:
            fn = self._cleanups.pop()
            try:
                fn()
            except Exception:
                pass
        self._plugins.clear()

    def register_plugin(self, plugin_id: str, plugin: Any) -> None:
        self._plugins[plugin_id] = plugin

    @property
    def plugins(self) -> dict[str, Any]:
        return dict(self._plugins)

    @property
    def services(self) -> Iterable[str]:
        return tuple(self._services)


async def maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable):
        return await value
    return value
