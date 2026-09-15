from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from openrd.core.context import Context
from openrd.db.store import get_store
from openrd.settings import settings


class SearchPolicy:
    def __init__(self) -> None:
        self.store = get_store()
        self.project_id: str | None = None

    def bind(self, project_id: str) -> None:
        self.project_id = project_id

    def allowed_types(self) -> dict[str, Any]:
        assert self.project_id
        recent = self.store.recent_hypothesis_types(self.project_id, settings.refine_window)
        lines = [h.get("line_id") or h.get("mechanism") for h in recent]
        counts = Counter(lines)
        blocked_refine_lines = {ln for ln, c in counts.items() if c >= settings.refine_max_in_window}
        types = [h.get("type") for h in recent]
        if types.count("refine") >= 3:
            prefer = ["explore", "pivot"]
        else:
            prefer = ["explore", "pivot", "refine"]
        # UCB over lines by virtual_score
        by_line: dict[str, list[float]] = defaultdict(list)
        for h in self.store.list_hypotheses(self.project_id):
            if h.get("virtual_score") is not None:
                by_line[h.get("line_id") or "x"].append(float(h["virtual_score"]))
        n_total = max(1, sum(len(v) for v in by_line.values()))
        ucb = {}
        for ln, vals in by_line.items():
            mean = sum(vals) / len(vals)
            ucb[ln] = mean + math.sqrt(2 * math.log(n_total) / len(vals))
        return {
            "prefer": prefer,
            "blocked_refine_lines": list(blocked_refine_lines),
            "ucb": ucb,
            "must_include_explore_or_pivot": True,
        }

    def filter_portfolio(self, hyps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        policy = self.allowed_types()
        out = []
        seen_lines = set()
        has_div = False
        for h in hyps:
            line = h.get("line") or h.get("mechanism")
            t = h.get("type") or "explore"
            if t == "refine" and line in policy["blocked_refine_lines"]:
                continue
            if line in seen_lines and t == "refine":
                continue
            seen_lines.add(line)
            if t in ("pivot", "explore"):
                has_div = True
            out.append(h)
        if out and not has_div:
            out[0]["type"] = "explore"
        return out


class Plugin:
    id = "rnd.search_policy"
    provides = ["search_policy"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_policy", SearchPolicy())
