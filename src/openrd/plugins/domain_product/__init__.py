from __future__ import annotations

from openrd.core.context import Context


class ProductDomain:
    name = "product_eval"
    hints = (
        "Respect hard constraints before optimizing the secondary metric. "
        "Never promote a treatment that breaks the safety/quality floor. "
        "Print METRICS JSON with every named KPI."
    )


class Plugin:
    id = "domain.product_eval"
    provides = ["domain_product"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("domain_product", ProductDomain())
