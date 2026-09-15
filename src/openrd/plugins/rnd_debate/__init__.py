from __future__ import annotations

import asyncio
from typing import Any

from openrd.core.context import Context
from openrd.util.text import extract_json

ROLES = {
    "steelman": "Argue why this hypothesis could win. List concrete mechanisms and risks you accept.",
    "redteam": "Destroy this hypothesis. Failure modes, leakage, noise-floor, cemetery overlap.",
    "novelty": "Is this actually new vs champion and cemetery? If it is a λ-tweak, say so.",
}


class Debate:
    def __init__(self) -> None:
        self.ctx: Context | None = None

    def bind(self, ctx: Context) -> None:
        self.ctx = ctx

    async def run(self, hyp: dict[str, Any], n_think: int = 3) -> dict[str, Any]:
        assert self.ctx
        llm = self.ctx.require("llm")
        roles = list(ROLES.items())[: max(1, min(n_think, 3))]

        async def one(role: str, instruction: str) -> dict[str, Any]:
            res = await llm.complete(
                "researcher" if role != "redteam" else "critic",
                [
                    {
                        "role": "user",
                        "content": f"ROLE={role}\n{instruction}\n\nHYPOTHESIS:\n{hyp}",
                    }
                ],
                system="Return JSON {verdict:support|reject|revise, points:[str], risk:str}",
                json_mode=True,
                temperature=0.7,
            )
            try:
                return {"role": role, **extract_json(res.text)}
            except Exception:
                return {"role": role, "verdict": "revise", "points": [res.text[:500]]}

        opinions = await asyncio.gather(*[one(r, ins) for r, ins in roles])
        rejects = sum(1 for o in opinions if o.get("verdict") == "reject")
        supports = sum(1 for o in opinions if o.get("verdict") == "support")
        veto = rejects >= 2 or (rejects == 1 and supports == 0)
        return {"opinions": opinions, "veto": veto, "supports": supports, "rejects": rejects}


class Plugin:
    id = "rnd.debate"
    provides = ["debate"]
    requires = ["llm"]

    def apply(self, ctx: Context) -> None:
        svc = Debate()
        svc.bind(ctx)
        ctx.provide("debate", svc)
