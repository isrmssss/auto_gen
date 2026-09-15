from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

from openrd.core.context import Context
from openrd.engine.hw import probe
from openrd.settings import settings


class Scheduler:
    def __init__(self) -> None:
        self.think = asyncio.Semaphore(4)
        self.exec = asyncio.Semaphore(1)
        self.last: dict[str, Any] = {}

    def configure(self, think_slots: int, exec_slots: int) -> dict[str, Any]:
        snap = probe(settings.default_exec_memory_frac, exec_slots)
        think = max(1, min(think_slots, snap.recommended_think_slots))
        exec_n = min(exec_slots, snap.recommended_exec_slots)
        if exec_n < 1:
            exec_n = 0
        self.think = asyncio.Semaphore(think)
        self.exec = asyncio.Semaphore(max(1, exec_n) if exec_n else 1)
        self.last = {
            **snap.__dict__,
            "think_slots": think,
            "exec_slots": exec_n,
        }
        return self.last

    async def run_think(self, fn: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        async with self.think:
            return await fn()

    async def run_exec(self, fn: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        if self.last.get("exec_slots", 1) == 0:
            raise RuntimeError(self.last.get("reason") or "exec refused by hardware gate")
        async with self.exec:
            snap = probe(settings.default_exec_memory_frac, 1)
            if not snap.can_launch_exec:
                raise RuntimeError(snap.reason)
            return await fn()


class Plugin:
    id = "scheduler.hw"
    provides = ["scheduler"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("scheduler", Scheduler())
