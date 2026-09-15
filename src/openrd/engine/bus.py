from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator

from openrd.db.store import Store, get_store


class EventBus:
    """Journal + in-process fan-out for WebSocket subscribers."""

    def __init__(self, store: Store | None = None) -> None:
        self.store = store or get_store()
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def emit(
        self,
        project_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        agent_id: str | None = None,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        event = self.store.append_event(
            project_id, event_type, payload=payload, agent_id=agent_id, node_id=node_id
        )
        async with self._lock:
            queues = list(self._subs.get(project_id, []))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                q.put_nowait(event)
        return event

    async def subscribe(self, project_id: str) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subs[project_id].append(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            async with self._lock:
                if q in self._subs.get(project_id, []):
                    self._subs[project_id].remove(q)


_BUS: EventBus | None = None


def get_bus() -> EventBus:
    global _BUS
    if _BUS is None:
        _BUS = EventBus()
    return _BUS


def reset_bus(store: Store | None = None) -> EventBus:
    global _BUS
    _BUS = EventBus(store)
    return _BUS
