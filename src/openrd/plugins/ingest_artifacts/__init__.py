from __future__ import annotations

from pathlib import Path

from openrd.core.context import Context
from openrd.db.store import get_store


class ArtifactService:
    def __init__(self) -> None:
        self.store = get_store()
        self.ctx: Context | None = None
        self.project_id: str | None = None

    def bind(self, ctx: Context, project_id: str) -> None:
        self.ctx = ctx
        self.project_id = project_id

    def ingest_file(self, path: Path, filename: str) -> dict:
        assert self.ctx and self.project_id
        parsed = self.ctx.require("ingest").ingest_path(path)
        archive = self.ctx.require("archive")
        for i, chunk in enumerate(parsed.get("chunks") or []):
            archive.add("paper", f"{filename}#{i}", chunk)
        for claim in parsed.get("claims") or []:
            archive.add("claim", filename, claim)
        return parsed


class Plugin:
    id = "ingest.user_artifacts"
    provides = ["artifacts"]
    requires = ["ingest", "archive"]

    def apply(self, ctx: Context) -> None:
        svc = ArtifactService()
        if ctx.project_id:
            svc.bind(ctx, ctx.project_id)
        ctx.provide("artifacts", svc)
