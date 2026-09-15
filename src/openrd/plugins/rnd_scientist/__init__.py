from __future__ import annotations

from typing import Any

from openrd.core.context import Context
from openrd.util.text import extract_json

SYS = """You are a senior researcher generating implementable hypotheses.
Follow 4 steps: (1) analyze current champion weaknesses (2) key problem (3) hypothesis with MECHANISM
(4) LLM-codeable sketch. Taxonomy type = refine|pivot|explore|validate.
JSON:
{
  "analysis": str,
  "key_problem": str,
  "hypotheses": [
     {"type": "explore", "line": str, "mechanism": str, "text": str, "sketch": str}
  ]
}
Generate 3 diverse hypotheses of DIFFERENT types. No id-specific hacks. No naive baselines if champion is already non-trivial.
"""


class Scientist:
    def __init__(self) -> None:
        self.ctx: Context | None = None

    def bind(self, ctx: Context) -> None:
        self.ctx = ctx

    async def propose(self, phase_note: str = "") -> list[dict[str, Any]]:
        assert self.ctx
        brief = self.ctx.require("compiler").brief("ideate", phase_note)
        llm = self.ctx.require("llm")
        res = await llm.complete(
            "orchestrator",
            [{"role": "user", "content": brief + "\n\nPropose hypotheses now."}],
            system=SYS,
            json_mode=True,
        )
        data = extract_json(res.text)
        hyps = data.get("hypotheses") or []
        out = []
        for h in hyps:
            out.append(
                {
                    "type": h.get("type") or "explore",
                    "line": h.get("line") or h.get("mechanism") or "line",
                    "mechanism": h.get("mechanism") or "",
                    "text": h.get("text") or "",
                    "sketch": h.get("sketch") or "",
                    "analysis": data.get("analysis"),
                    "key_problem": data.get("key_problem"),
                }
            )
        return out


class Plugin:
    id = "rnd.scientist"
    provides = ["scientist"]
    requires = ["llm", "compiler"]

    def apply(self, ctx: Context) -> None:
        svc = Scientist()
        svc.bind(ctx)
        ctx.provide("scientist", svc)
