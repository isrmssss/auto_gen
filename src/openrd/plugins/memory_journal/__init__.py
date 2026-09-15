from __future__ import annotations

from typing import Any

from openrd.core.context import Context
from openrd.db.store import get_store
from openrd.engine.bus import get_bus


class JournalService:
    def __init__(self) -> None:
        self.store = get_store()
        self.bus = get_bus()
        self.project_id: str | None = None

    def bind(self, project_id: str) -> None:
        self.project_id = project_id

    async def write(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        agent_id: str | None = None,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.project_id:
            raise RuntimeError("journal not bound")
        return await self.bus.emit(self.project_id, event_type, payload, agent_id, node_id)

    def replay(self, after_seq: int = 0) -> list[dict[str, Any]]:
        if not self.project_id:
            return []
        return self.store.list_events(self.project_id, after_seq=after_seq, limit=10000)

    def get(self, seq: int) -> dict[str, Any] | None:
        if not self.project_id:
            return None
        rows = self.store.list_events(self.project_id, after_seq=seq - 1, limit=1)
        return rows[0] if rows and rows[0]["seq"] == seq else None


class Plugin:
    id = "memory.journal"
    provides = ["journal"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("journal", JournalService())
