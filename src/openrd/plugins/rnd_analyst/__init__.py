from __future__ import annotations

from typing import Any

from openrd.core.context import Context
from openrd.util.text import extract_json


class Analyst:
    def __init__(self) -> None:
        self.ctx: Context | None = None

    def bind(self, ctx: Context) -> None:
        self.ctx = ctx

    async def analyze(
        self,
        treatment: dict[str, Any],
        champion: dict[str, Any] | None,
        log_tail: str,
    ) -> dict[str, Any]:
        assert self.ctx
        llm = self.ctx.require("llm")
        res = await llm.complete(
            "orchestrator",
            [
                {
                    "role": "user",
                    "content": (
                        "JSON {persist:[str], fixed:[str], regress:[str], lesson:str, "
                        "cemetery_class:str|null, promote:bool, next_type:refine|pivot|explore}\n"
                        f"TREATMENT={treatment}\nCHAMPION={champion}\nLOG={log_tail[-3000:]}"
                    ),
                }
            ],
            json_mode=True,
        )
        try:
            return extract_json(res.text)
        except Exception:
            return {
                "persist": [],
                "fixed": [],
                "regress": [],
                "lesson": log_tail[:400],
                "cemetery_class": None,
                "promote": False,
                "next_type": "explore",
            }


class Plugin:
    id = "rnd.analyst"
    provides = ["analyst"]
    requires = ["llm", "tracker"]

    def apply(self, ctx: Context) -> None:
        svc = Analyst()
        svc.bind(ctx)
        ctx.provide("analyst", svc)
