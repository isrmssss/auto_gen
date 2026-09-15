from __future__ import annotations

from typing import Any

import httpx

from openrd.core.context import Context
from openrd.util.canon import canon_query, canon_url


class S2Service:
    async def search(self, query: str, count: int = 8) -> list[dict[str, Any]]:
        params = {
            "query": query,
            "limit": count,
            "fields": "title,abstract,year,citationCount,url,externalIds,openAccessPdf,venue",
        }
        headers = {"User-Agent": "OpenRD/0.1 (local research agent)"}
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
        hits = []
        for item in data.get("data") or []:
            url = item.get("url") or ""
            pdf = ((item.get("openAccessPdf") or {}) or {}).get("url")
            hits.append(
                {
                    "title": item.get("title") or "",
                    "url": url,
                    "url_canon": canon_url(url or pdf or ""),
                    "snippet": (item.get("abstract") or "")[:800],
                    "year": item.get("year"),
                    "citations": item.get("citationCount") or 0,
                    "venue": item.get("venue"),
                    "pdf": pdf,
                    "source": "s2",
                    "query_canon": canon_query(query),
                }
            )
        return hits


class Plugin:
    id = "search.s2"
    provides = ["search_s2"]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_s2", S2Service())
