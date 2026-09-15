from __future__ import annotations

from typing import Any

import httpx

from openrd.core.context import Context
from openrd.plugins.search_common import scrub_injection
from openrd.settings import settings
from openrd.util.canon import canon_query, canon_url


class SearxService:
    def __init__(self) -> None:
        self.base = settings.searxng_url.rstrip("/")

    async def search(self, query: str, count: int = 8) -> list[dict[str, Any]]:
        params = {"q": query, "format": "json", "pageno": 1}
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.get(f"{self.base}/search", params=params)
            r.raise_for_status()
            data = r.json()
        hits = []
        for item in (data.get("results") or [])[:count]:
            hits.append(
                {
                    "title": item.get("title") or "",
                    "url": item.get("url") or "",
                    "url_canon": canon_url(item.get("url") or ""),
                    "snippet": scrub_injection(item.get("content") or ""),
                    "source": "searxng",
                    "engine": item.get("engine"),
                    "query_canon": canon_query(query),
                }
            )
        return hits


class Plugin:
    id = "search.searxng"
    provides = ["search_web"]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_web", SearxService())
