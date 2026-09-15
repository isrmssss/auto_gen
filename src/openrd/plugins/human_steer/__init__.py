from __future__ import annotations

from collections import deque
from typing import Any

from openrd.core.context import Context
from openrd.db.store import get_store


class HumanInbox:
    def __init__(self) -> None:
        self.store = get_store()
        self.project_id: str | None = None
        self.pending: deque[dict[str, Any]] = deque()
        self.pause = False
        self.stop = False
        self.rollback_to: str | None = None

    def bind(self, project_id: str) -> None:
        self.project_id = project_id

    def push(self, kind: str, content: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self.project_id
        msg = {"kind": kind, "content": content, **(extra or {})}
        self.pending.append(msg)
        self.store.add_human_message(self.project_id, "user", f"{kind}: {content}")
        if kind == "pause":
            self.pause = True
        if kind == "resume":
            self.pause = False
        if kind == "stop":
            self.stop = True
        if kind == "rollback":
            self.rollback_to = extra.get("node_id") if extra else content
        return msg

    def drain(self) -> list[dict[str, Any]]:
        items = list(self.pending)
        self.pending.clear()
        return items


class Plugin:
    id = "human.steer"
    provides = ["human"]
    requires = ["journal"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("human", HumanInbox())
