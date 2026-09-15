from __future__ import annotations

from typing import Any

from openrd.core.context import Context
from openrd.util.text import extract_json


class VirtualEval:
    def __init__(self) -> None:
        self.ctx: Context | None = None

    def bind(self, ctx: Context) -> None:
        self.ctx = ctx

    async def pick(self, hyps: list[dict[str, Any]]) -> dict[str, Any]:
        assert self.ctx
        if len(hyps) == 1:
            hyps[0]["virtual_score"] = hyps[0].get("virtual_score") or 7.0
            return {"winner": hyps[0], "scored": hyps}
        llm = self.ctx.require("llm")
        res = await llm.complete(
            "critic",
            [
                {
                    "role": "user",
                    "content": (
                        "Score each hypothesis 0-10 novelty, feasibility, impact. "
                        "JSON {scores:[{i, novelty, feasibility, impact, note}]}\n"
                        f"{hyps}"
                    ),
                }
            ],
            json_mode=True,
        )
        try:
            data = extract_json(res.text)
            scores = data.get("scores") or []
        except Exception:
            scores = []
        scored = []
        for i, h in enumerate(hyps):
            match = next((s for s in scores if s.get("i") == i), None) or (
                scores[i] if i < len(scores) else {}
            )
            n = float(match.get("novelty") or 5)
            f = float(match.get("feasibility") or 5)
            imp = float(match.get("impact") or 5)
            total = n * 0.3 + f * 0.3 + imp * 0.4
            item = dict(h)
            item["virtual_score"] = round(total, 3)
            item["virtual_breakdown"] = {"novelty": n, "feasibility": f, "impact": imp}
            scored.append(item)
        scored.sort(key=lambda x: x["virtual_score"], reverse=True)
        return {"winner": scored[0], "scored": scored}


class Plugin:
    id = "rnd.virtual_eval"
    provides = ["virtual_eval"]
    requires = ["llm"]

    def apply(self, ctx: Context) -> None:
        svc = VirtualEval()
        svc.bind(ctx)
        ctx.provide("virtual_eval", svc)
