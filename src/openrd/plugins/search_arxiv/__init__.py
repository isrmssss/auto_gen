from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import httpx

from openrd.core.context import Context
from openrd.util.canon import canon_query, canon_url

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
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.get("https://export.arxiv.org/api/query", params=params)
            r.raise_for_status()
            root = ET.fromstring(r.text)
        hits = []
        for entry in root.findall("a:entry", NS):
            link = ""
            pdf = ""
            for l in entry.findall("a:link", NS):
                href = l.attrib.get("href") or ""
                if l.attrib.get("type") == "application/pdf":
                    pdf = href
                elif l.attrib.get("rel") == "alternate":
                    link = href
            title = (entry.findtext("a:title", default="", namespaces=NS) or "").strip()
            summary = (entry.findtext("a:summary", default="", namespaces=NS) or "").strip()
            published = entry.findtext("a:published", default="", namespaces=NS) or ""
            hits.append(
                {
                    "title": title,
                    "url": link or pdf,
                    "url_canon": canon_url(link or pdf),
                    "snippet": summary[:800],
                    "pdf": pdf,
                    "published": published,
                    "source": "arxiv",
                    "query_canon": canon_query(query),
                }
            )
        return hits


class Plugin:
    id = "search.arxiv"
    provides = ["search_arxiv"]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_arxiv", ArxivService())
