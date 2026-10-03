from __future__ import annotations

from typing import Any

import httpx

from openrd.core.context import Context
from openrd.plugins.search_common import make_hit


def _abstract(item: dict[str, Any]) -> str:
    plain = item.get("abstract")
    if isinstance(plain, str) and plain:
        return plain
    inverted = item.get("abstract_inverted_index")
    if not isinstance(inverted, dict):
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted.items():
        for pos in positions or []:
            words[int(pos)] = word
    return " ".join(words[i] for i in sorted(words))


class OpenAlexService:
    async def search(self, query: str, count: int = 8) -> list[dict[str, Any]]:
        params = {
            "search": query,
            "per_page": count,
            "sort": "cited_by_count:desc",
            "mailto": "openrd@localhost",
        }
        async with httpx.AsyncClient(timeout=40, follow_redirects=False) as client:
            response = await client.get("https://api.openalex.org/works", params=params)
            response.raise_for_status()
            data = response.json()
        hits = []
        for item in data.get("results") or []:
            location = item.get("primary_location") or {}
            url = location.get("landing_page_url") or item.get("id") or ""
            ids = item.get("ids") or {}
            hits.append(
                make_hit(
                    title=item.get("display_name") or "",
                    url=url,
                    query=query,
                    source="openalex",
                    snippet=_abstract(item),
                    pdf=location.get("pdf_url"),
                    year=item.get("publication_year"),
                    citations=item.get("cited_by_count") or 0,
                    doi=ids.get("doi") or item.get("doi") or "",
                    pmcid=str(ids.get("pmcid") or "").removeprefix("https://www.ncbi.nlm.nih.gov/pmc/articles/"),
                )
            )
        return hits


class Plugin:
    id = "search.openalex"
    provides = ["search_openalex"]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_openalex", OpenAlexService())
