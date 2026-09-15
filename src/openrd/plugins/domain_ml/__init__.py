from __future__ import annotations

from openrd.core.context import Context


class MLDomain:
    name = "ml_competition"
    hints = (
        "Use a fixed train/val split. Screen on a sample. "
        "Do not leak the test labels. Prefer compound methods over default GBDT. "
        "Print METRICS:{\"primary\": <float>} where primary matches the contest metric."
    )


class Plugin:
    id = "domain.ml_competition"
    provides = ["domain_ml"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("domain_ml", MLDomain())
