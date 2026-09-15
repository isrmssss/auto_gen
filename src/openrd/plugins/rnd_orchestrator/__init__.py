from __future__ import annotations

from openrd.core.context import Context
from openrd.engine.worker import get_runtime


class OrchestratorHandle:
    def runtime(self, project_id: str):
        return get_runtime(project_id)


class Plugin:
    id = "rnd.orchestrator"
    provides = ["orchestrator"]
    requires = ["journal", "compiler", "scheduler"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("orchestrator", OrchestratorHandle())
