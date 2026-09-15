from __future__ import annotations

from openrd.core.context import Context


class GeneralDomain:
    name = "general_research"
    hints = (
        "Define a verifier: a function or script that returns METRICS.primary "
        "(0 fail / 1 success, or a distance). Prefer small constructive experiments. "
        "Do not claim a millennium prize; report partial invariants and failed attempts."
    )


class Plugin:
    id = "domain.general_research"
    provides = ["domain_general"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("domain_general", GeneralDomain())
