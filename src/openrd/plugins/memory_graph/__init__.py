from __future__ import annotations

from typing import Any

from openrd.core.context import Context
from openrd.db.store import get_store
from openrd.util.canon import fingerprint_text


class GraphService:
    def __init__(self) -> None:
        self.store = get_store()
        self.project_id: str | None = None

    def bind(self, project_id: str) -> None:
        self.project_id = project_id

    def node(self, kind: str, label: str, data: dict[str, Any] | None = None, node_id: str | None = None) -> str:
        assert self.project_id
        nid = node_id or fingerprint_text(self.project_id, kind, label)
        self.store.add_graph_node(
            {
                "id": nid,
                "project_id": self.project_id,
                "kind": kind,
                "label": label,
                "data": data or {},
            }
        )
        return nid

    def edge(self, src: str, dst: str, rel: str) -> None:
        assert self.project_id
        self.store.add_graph_edge(self.project_id, src, dst, rel)

    def snapshot(self) -> dict[str, Any]:
        assert self.project_id
        return self.store.get_graph(self.project_id)


class Plugin:
    id = "memory.graph"
    provides = ["graph"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("graph", GraphService())
