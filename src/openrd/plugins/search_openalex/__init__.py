from __future__ import annotations

from typing import Any

import httpx

from openrd.core.context import Context
from openrd.util.canon import canon_query, canon_url


class OpenAlexService:
    async def search(self, query: str, count: int = 8) -> list[dict[str, Any]]:
        params = {
            "search": query,
            "per_page": count,
            "sort": "cited_by_count:desc",
            "mailto": "openrd@localhost",
        }
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.get("https://api.openalex.org/works", params=params)
            r.raise_for_status()
            data = r.json()
        hits = []
        for item in data.get("results") or []:
            url = (item.get("primary_location") or {}).get("landing_page_url") or item.get("id") or ""
            pdf = (item.get("primary_location") or {}).get("pdf_url")
            hits.append(
                {
                    "title": item.get("display_name") or "",
                    "url": url,
                    "url_canon": canon_url(url or ""),
                    "snippet": (item.get("abstract") or "")[:800]
                    if isinstance(item.get("abstract"), str)
                    else "",
                    "year": (item.get("publication_year")),
                    "citations": item.get("cited_by_count") or 0,
                    "pdf": pdf,
                    "source": "openalex",
                    "query_canon": canon_query(query),
                }
            )
        return hits


class Plugin:
    id = "search.openalex"
    provides = ["search_openalex"]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_openalex", OpenAlexService())
