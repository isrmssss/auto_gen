from __future__ import annotations

from openrd.core.context import Context
from openrd.db.store import get_store
from openrd.settings import settings
from openrd.util.text import clip_tokens


CORE_KEYS = ("goal", "champion", "open_questions", "bans", "budget", "kpi")


class CoreMemory:
    def __init__(self) -> None:
        self.store = get_store()
        self.project_id: str | None = None

    def bind(self, project_id: str) -> None:
        self.project_id = project_id

    def get(self) -> dict[str, str]:
        assert self.project_id
        return self.store.get_memory(self.project_id)

    def patch(self, key: str, content: str) -> None:
        assert self.project_id
        clipped = clip_tokens(content, settings.prompt_core_token_budget // max(1, len(CORE_KEYS)))
        self.store.patch_memory(self.project_id, key, clipped)

    def render(self) -> str:
        blocks = self.get()
        parts = ["# Core memory (do not exceed; patch instead of appending history)"]
        for key in CORE_KEYS:
            parts.append(f"## {key}\n{blocks.get(key, '')}")
        text = "\n\n".join(parts)
        return clip_tokens(text, settings.prompt_core_token_budget)


class Plugin:
    id = "memory.core"
    provides = ["memory_core"]
    requires = ["journal"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("memory_core", CoreMemory())
