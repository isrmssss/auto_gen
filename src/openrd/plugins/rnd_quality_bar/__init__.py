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
_EMPTY_CHAMPION = {"", "(none yet)", "(none)", "none", "null"}


def champion_is_set(champion: str) -> bool:
    return (champion or "").strip().lower() not in _EMPTY_CHAMPION


def expand_writeup(mechanism: str, text: str, metric: str = "primary") -> str:
    """One expansion so a short note states mechanism, trigger, freeze, and KPI effect."""
    body = (text or "").strip()
    if len(body.split()) >= 25:
        return body
    addition = (
        f"Mechanism: {mechanism or 'the stated idea'}. "
        "Trigger: the data card or the user note shows this lever is available. "
        "Frozen: components that are not part of this mechanism stay unchanged. "
        f"Expected KPI effect: move {metric or 'primary'} in the goal direction on a screen split."
    )
    return f"{body} {addition}".strip()


class QualityBar:
    def __init__(self) -> None:
        self.ctx: Context | None = None
        self.rigor = "high"

    def bind(self, ctx: Context, rigor: str = "high") -> None:
        self.ctx = ctx
        self.rigor = rigor

    def cheap_check(
        self,
        mechanism: str,
        text: str,
        champion: str = "",
        has_data_card: bool = False,
    ) -> dict[str, Any]:
        reasons = []
        blob = f"{mechanism}\n{text}"
        naive = bool(NAIVE.search(mechanism.strip()))
        if self.rigor in {"high", "extreme"} and naive:
            reasons.append(
                "mechanism is a bare baseline; require a compound (adapter, loss, data, calibration)"
            )
        thin = len(text.split()) < 25 and self.rigor != "low"
        first_screen = has_data_card and not champion_is_set(champion) and not naive
        if thin and not first_screen:
            reasons.append(
                "write-up too thin — need mechanism, trigger, what is frozen, expected KPI effect"
            )
        if "if id=" in blob.lower() or "hardcode" in blob.lower():
            reasons.append("looks like an id-specific hack")
        return {"ok": not reasons, "reasons": reasons}

    async def judge(
        self,
        goal: str,
        mechanism: str,
        text: str,
        champion: str,
        has_data_card: bool = False,
    ) -> dict[str, Any]:
        cheap = self.cheap_check(
            mechanism, text, champion=champion, has_data_card=has_data_card
        )
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
