from __future__ import annotations

from typing import Any

import httpx

from openrd.core.context import Context
from openrd.plugins.search_common import make_hit


class S2Service:
    async def search(self, query: str, count: int = 8) -> list[dict[str, Any]]:
        params = {
            "query": query,
            "limit": count,
            "fields": "title,abstract,year,citationCount,url,externalIds,openAccessPdf,venue",
        }
        headers = {"User-Agent": "OpenRD/0.1 (local research agent)"}
        async with httpx.AsyncClient(timeout=40, follow_redirects=False) as client:
            response = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        hits = []
        for item in data.get("data") or []:
            ids = item.get("externalIds") or {}
            url = item.get("url") or ""
            pdf = ((item.get("openAccessPdf") or {}) or {}).get("url")
            hits.append(
                make_hit(
                    title=item.get("title") or "",
                    url=url,
                    query=query,
                    source="s2",
                    snippet=item.get("abstract") or "",
                    pdf=pdf,
                    year=item.get("year"),
                    citations=item.get("citationCount") or 0,
                    doi=ids.get("DOI") or "",
                    arxiv_id=ids.get("ArXiv") or "",
                    pmcid=ids.get("PubMedCentral") or "",
                    venue=item.get("venue") or "",
                )
            )
        return hits


class Plugin:
    id = "search.s2"
    provides = ["search_s2"]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_s2", S2Service())
