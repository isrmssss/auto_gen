from __future__ import annotations

from typing import Any

import httpx

from openrd.core.context import Context
from openrd.plugins.search_common import make_hit


class GithubService:
    async def search(self, query: str, count: int = 8) -> list[dict[str, Any]]:
        params = {"q": query, "sort": "stars", "order": "desc", "per_page": count}
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "OpenRD/0.1",
        }
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.get("https://api.github.com/search/repositories", params=params, headers=headers)
            if r.status_code == 403:
                return []
            r.raise_for_status()
            data = r.json()
        hits = []
        for item in data.get("items") or []:
            url = item.get("html_url") or ""
            hits.append(
                make_hit(
                    title=item.get("full_name") or "",
                    url=url,
                    query=query,
                    source="github",
                    snippet=item.get("description") or "",
                    stars=item.get("stargazers_count") or 0,
                    language=item.get("language") or "",
                )
            )
        return hits


class Plugin:
    id = "search.github"
    provides = ["search_github"]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_github", GithubService())
