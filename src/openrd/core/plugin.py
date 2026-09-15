from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class Plugin(Protocol):
    id: str
    provides: list[str]
    requires: list[str]

    def apply(self, ctx: Any) -> None: ...


@dataclass
class PluginManifest:
    id: str
    provides: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    title: str = ""
    description: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    when_to_use: str = ""
    bundle: str = "core"
    optional: bool = False
    module: str = ""
    class_name: str = "Plugin"

    def to_llm_doc(self) -> str:
        tools = ", ".join(t.get("name", "") for t in self.tools) or "(no tools)"
        return (
            f"- `{self.id}` [{self.bundle}]: {self.title or self.id}. "
            f"{self.description} When: {self.when_to_use or 'always available'}. "
            f"Tools: {tools}."
        )
