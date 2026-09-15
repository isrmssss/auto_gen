from __future__ import annotations

import re
from typing import Any

from openrd.core.context import Context
from openrd.util.text import extract_json

NAIVE = re.compile(
    r"^(just |simply )?(bert|logreg|logistic regression|linear regression|"
    r"xgboost default|random forest|lstm|fine-tune bert)\s*$",
    re.I,
)


class QualityBar:
    def __init__(self) -> None:
        self.ctx: Context | None = None
        self.rigor = "high"

    def bind(self, ctx: Context, rigor: str = "high") -> None:
        self.ctx = ctx
        self.rigor = rigor

    def cheap_check(self, mechanism: str, text: str) -> dict[str, Any]:
        reasons = []
        blob = f"{mechanism}\n{text}"
        if self.rigor in {"high", "extreme"} and NAIVE.search(mechanism.strip()):
            reasons.append("mechanism is a bare baseline; require a compound (adapter, loss, data, calibration)")
        if len(text.split()) < 25 and self.rigor != "low":
            reasons.append("write-up too thin — need mechanism, trigger, what is frozen, expected KPI effect")
        if "if id=" in text.lower() or "hardcode" in text.lower():
            reasons.append("looks like an id-specific hack")
        return {"ok": not reasons, "reasons": reasons}

    async def judge(self, goal: str, mechanism: str, text: str, champion: str) -> dict[str, Any]:
        cheap = self.cheap_check(mechanism, text)
        if not cheap["ok"]:
            return cheap
        if not self.ctx or self.rigor == "low":
            return cheap
        llm = self.ctx.require("llm")
        prompt = {
            "goal": goal,
            "champion": champion,
            "mechanism": mechanism,
            "idea": text,
            "instruction": (
                "JSON {ok:bool, compound:bool, novelty:0-10, reasons:[str]}. "
                "ok=false if this is a tiny refine of a known lever, a naive baseline, or lacks a mechanism."
            ),
        }
        try:
            res = await llm.complete(
                "critic",
                [{"role": "user", "content": str(prompt)}],
                system="You are a harsh R&D critic. Prefer compound SOTA-grade ideas.",
                json_mode=True,
            )
            data = extract_json(res.text)
            return {
                "ok": bool(data.get("ok")) and bool(data.get("compound", True)),
                "reasons": data.get("reasons") or [],
                "novelty": data.get("novelty"),
            }
        except Exception:
            return cheap


class Plugin:
    id = "rnd.quality_bar"
    provides = ["quality_bar"]
    requires = ["llm"]

    def apply(self, ctx: Context) -> None:
        svc = QualityBar()
        svc.bind(ctx)
        ctx.provide("quality_bar", svc)
