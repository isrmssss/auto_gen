from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from openrd.core.context import Context
from openrd.plugins.search_common import FULLTEXT_HOSTS, FetchDenied, fetch_text, make_hit

NS = {"a": "http://www.w3.org/2005/Atom"}


class ArxivService:
    async def search(self, query: str, count: int = 8) -> list[dict[str, Any]]:
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": count,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        async with httpx.AsyncClient(timeout=40, follow_redirects=False) as client:
            response = await client.get("https://export.arxiv.org/api/query", params=params)
            response.raise_for_status()
            root = ET.fromstring(response.text)
        hits = []
        for entry in root.findall("a:entry", NS):
            link = ""
            pdf = ""
            for item in entry.findall("a:link", NS):
                href = item.attrib.get("href") or ""
                if item.attrib.get("type") == "application/pdf":
                    pdf = href
                elif item.attrib.get("rel") == "alternate":
                    link = href
            title = (entry.findtext("a:title", default="", namespaces=NS) or "").strip()
            summary = (entry.findtext("a:summary", default="", namespaces=NS) or "").strip()
            published = entry.findtext("a:published", default="", namespaces=NS) or ""
            aid = ""
            id_text = entry.findtext("a:id", default="", namespaces=NS) or ""
            if "/abs/" in id_text:
                aid = id_text.rsplit("/abs/", 1)[-1]
            hits.append(
                make_hit(
                    title=title,
                    url=link or pdf,
                    query=query,
                    source="arxiv",
                    snippet=summary,
                    pdf=pdf or None,
                    arxiv_id=aid,
                    published=published,
                )
            )
        return hits

    async def read(self, hit: dict[str, Any]) -> dict[str, Any]:
        """Pull HTML full text from ar5iv, then arXiv HTML. Never an arbitrary URL."""
        aid = re.sub(r"v\d+$", "", (hit.get("arxiv_id") or "").strip(), flags=re.I)
        if not aid:
            return {"ok": False, "reason": "no arxiv id"}
        urls = [
            f"https://ar5iv.labs.arxiv.org/html/{aid}",
            f"https://arxiv.org/html/{aid}",
        ]
        last = "unavailable"
        for url in urls:
            try:
                text = await fetch_text(url, hosts=FULLTEXT_HOSTS)
            except (FetchDenied, httpx.HTTPError) as exc:
                last = str(exc)[:180]
                continue
            if text and len(text) > 80:
                return {"ok": True, "text": text, "fetched": url, "arxiv_id": aid}
            last = "empty"
        return {"ok": False, "reason": last, "arxiv_id": aid}


class Plugin:
    id = "search.arxiv"
    provides = ["search_arxiv"]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_arxiv", ArxivService())
