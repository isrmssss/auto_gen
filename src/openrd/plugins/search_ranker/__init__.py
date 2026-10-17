from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from openrd.core.context import Context
from openrd.util.text import tokenize

_GENERIC = {
    "a",
    "an",
    "the",
    "of",
    "and",
    "or",
    "for",
    "to",
    "in",
    "on",
    "with",
    "by",
    "from",
    "beat",
    "beating",
    "state",
    "art",
    "method",
    "methods",
    "paper",
    "papers",
    "github",
    "implementation",
    "alternative",
    "approaches",
    "approach",
    "evaluation",
    "protocol",
    "feature",
    "engineering",
    "limitation",
    "limitations",
    "fails",
    "fail",
    "why",
    "using",
    "use",
    "based",
    "via",
    "new",
    "vs",
    "into",
    "than",
    "this",
    "that",
    "task",
    "stated",
}
_METRICS = {"rmsle", "rmse", "mae", "mape", "auc", "f1", "logloss", "accuracy"}


def focus_terms(focus: str) -> set[str]:
    terms = set()
    for token in tokenize(focus):
        if token in _METRICS or (len(token) >= 3 and token not in _GENERIC):
            terms.add(token)
    return terms


def _year(hit: dict[str, Any]) -> int | None:
    y = hit.get("year")
    if isinstance(y, int):
        return y
    pub = str(hit.get("published") or "")
    if len(pub) >= 4 and pub[:4].isdigit():
        return int(pub[:4])
    return None


class Ranker:
    def rank(
        self,
        hits: list[dict[str, Any]],
        now_year: int | None = None,
        *,
        focus: str = "",
    ) -> list[dict[str, Any]]:
        year_now = now_year or datetime.now(timezone.utc).year
        wanted = focus_terms(focus)
        seen: set[str] = set()
        scored = []
        approaches: list[str] = []
        for h in hits:
            key = h.get("paper_key") or h.get("url_canon") or h.get("url") or h.get("title")
            if not key or key in seen:
                continue
            seen.add(key)
            score = 0.0
            y = _year(h)
            if y:
                age = year_now - y
                if age <= 1:
                    score += 3
                elif age <= 2:
                    score += 1.5
                elif age > 4:
                    score -= 1
            cites = float(h.get("citations") or 0)
            stars = float(h.get("stars") or 0)
            score += min(4.0, (cites**0.5) / 4 + (stars**0.5) / 8)
            if h.get("pdf") or h.get("source") in ("arxiv", "s2", "openalex", "openreview", "eupmc"):
                score += 2
            if h.get("arxiv_id") or h.get("pmcid") or h.get("openreview_id"):
                score += 1.5
            if h.get("source") == "github" and stars >= 100:
                score += 1.5
            title = (h.get("title") or "").lower()
            blob = f"{title} {(h.get('snippet') or '').lower()}"
            overlap = wanted & set(tokenize(blob)) if wanted else set()
            if wanted and not overlap:
                continue
            score += 2.0 * len(overlap)
            diversity_bonus = 0.4 if not any(w in title for w in approaches[-3:]) else 0
            score += diversity_bonus
            approaches.append(title[:40])
            snippet = (h.get("snippet") or "").lower()
            if any(w in snippet for w in ("tutorial", "what is", "for beginners")):
                score -= 1.2
            h = dict(h)
            h["quality"] = round(score, 3)
            scored.append(h)
        scored.sort(key=lambda x: x["quality"], reverse=True)
        return scored


class Plugin:
    id = "search.ranker"
    provides = ["search_ranker"]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_ranker", Ranker())
