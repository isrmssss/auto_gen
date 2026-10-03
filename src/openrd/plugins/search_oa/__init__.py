"""Keyless scholarly sources. Full text stays on an allowlist."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from openrd.core.context import Context
from openrd.plugins.search_common import (
    FULLTEXT_HOSTS,
    FetchDenied,
    fetch_json,
    fetch_text,
    html_to_text,
    make_hit,
)

_UA = {"User-Agent": "OpenRD/0.1 (mailto:openrd@localhost)"}


def _year(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    text = str(value or "")
    return int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "value" in value:
            return _text(value.get("value"))
        return _text(value.get("#text") or value.get("@value") or value.get("text"))
    if isinstance(value, list):
        return " ".join(_text(item) for item in value if item)
    return str(value)


class CrossrefService:
    async def search(self, query: str, count: int = 5) -> list[dict[str, Any]]:
        data = await fetch_json(
            "https://api.crossref.org/works",
            params={
                "query": query,
                "rows": count,
                "select": "DOI,title,abstract,URL,issued,is-referenced-by-count",
            },
            headers=_UA,
        )
        hits = []
        for item in (data.get("message") or {}).get("items") or []:
            issued = ((item.get("issued") or {}).get("date-parts") or [[None]])[0]
            doi = item.get("DOI") or ""
            hits.append(
                make_hit(
                    title=_text(item.get("title")),
                    url=item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
                    query=query,
                    source="crossref",
                    snippet=html_to_text(_text(item.get("abstract"))),
                    year=_year(issued[0] if issued else None),
                    citations=int(item.get("is-referenced-by-count") or 0),
                    doi=doi,
                )
            )
        return hits


class DblpService:
    async def search(self, query: str, count: int = 5) -> list[dict[str, Any]]:
        data = await fetch_json(
            "https://dblp.org/search/publ/api",
            params={"q": query, "format": "json", "h": count},
            headers=_UA,
        )
        raw_hits = (((data.get("result") or {}).get("hits") or {}).get("hit")) or []
        if isinstance(raw_hits, dict):
            raw_hits = [raw_hits]
        hits = []
        for item in raw_hits:
            info = item.get("info") or {}
            ee = info.get("ee")
            url = _text(ee[0] if isinstance(ee, list) and ee else ee)
            hits.append(
                make_hit(
                    title=_text(info.get("title")),
                    url=url,
                    query=query,
                    source="dblp",
                    snippet=_text(info.get("venue")),
                    year=_year(info.get("year")),
                    doi=info.get("doi") or "",
                )
            )
        return hits


class OpenReviewService:
    async def search(self, query: str, count: int = 5) -> list[dict[str, Any]]:
        data = await fetch_json(
            "https://api2.openreview.net/notes/search",
            params={"term": query, "limit": count, "source": "forum"},
            headers=_UA,
        )
        notes = data.get("notes") or data.get("results") or []
        hits = []
        for note in notes:
            content = note.get("content") or {}
            nid = str(note.get("forum") or note.get("id") or "")
            if not nid:
                continue
            hits.append(
                make_hit(
                    title=_text(content.get("title")),
                    url=f"https://openreview.net/forum?id={nid}",
                    query=query,
                    source="openreview",
                    snippet=_text(content.get("abstract")),
                    pdf=f"https://openreview.net/pdf?id={nid}",
                    openreview_id=nid,
                )
            )
        return hits

    async def read(self, hit: dict[str, Any]) -> dict[str, Any]:
        oid = hit.get("openreview_id") or ""
        if not oid:
            return {"ok": False, "reason": "no openreview id"}
        url = f"https://openreview.net/pdf?id={oid}"
        try:
            text = await fetch_text(url, hosts=FULLTEXT_HOSTS)
        except (FetchDenied, httpx.HTTPError) as exc:
            return {"ok": False, "reason": str(exc)[:180], "openreview_id": oid}
        if len(text) < 80:
            return {"ok": False, "reason": "empty", "openreview_id": oid}
        return {"ok": True, "text": text, "fetched": url, "openreview_id": oid}


class EuropePmcService:
    async def search(self, query: str, count: int = 5) -> list[dict[str, Any]]:
        data = await fetch_json(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": query, "format": "json", "pageSize": count, "resultType": "core"},
            headers=_UA,
        )
        hits = []
        for item in ((data.get("resultList") or {}).get("result")) or []:
            pmcid = item.get("pmcid") or ""
            doi = item.get("doi") or ""
            url = (
                f"https://europepmc.org/article/PMC/{pmcid.removeprefix('PMC')}"
                if pmcid
                else (f"https://doi.org/{doi}" if doi else "")
            )
            hits.append(
                make_hit(
                    title=item.get("title") or "",
                    url=url,
                    query=query,
                    source="eupmc",
                    snippet=item.get("abstractText") or "",
                    year=_year(item.get("firstPublicationDate") or item.get("pubYear")),
                    citations=int(item.get("citedByCount") or 0),
                    doi=doi,
                    pmcid=pmcid,
                )
            )
        return hits

    async def read(self, hit: dict[str, Any]) -> dict[str, Any]:
        pmcid = (hit.get("pmcid") or "").upper()
        if not pmcid:
            return {"ok": False, "reason": "no pmcid"}
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
        try:
            text = await fetch_text(url, hosts=FULLTEXT_HOSTS)
        except (FetchDenied, httpx.HTTPError) as exc:
            return {"ok": False, "reason": str(exc)[:180], "pmcid": pmcid}
        if len(text) < 80:
            return {"ok": False, "reason": "empty", "pmcid": pmcid}
        return {"ok": True, "text": text, "fetched": url, "pmcid": pmcid}


class PubmedService:
    async def search(self, query: str, count: int = 5) -> list[dict[str, Any]]:
        found = await fetch_json(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={
                "db": "pubmed",
                "retmode": "json",
                "retmax": count,
                "term": query,
                "tool": "openrd",
                "email": "openrd@localhost",
            },
            headers=_UA,
        )
        ids = ((found.get("esearchresult") or {}).get("idlist")) or []
        if not ids:
            return []
        summary = await fetch_json(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={
                "db": "pubmed",
                "retmode": "json",
                "id": ",".join(ids),
                "tool": "openrd",
                "email": "openrd@localhost",
            },
            headers=_UA,
        )
        result = summary.get("result") or {}
        hits = []
        for pmid in ids:
            item = result.get(pmid) or {}
            if not isinstance(item, dict):
                continue
            hits.append(
                make_hit(
                    title=item.get("title") or "",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    query=query,
                    source="pubmed",
                    snippet=item.get("source") or "",
                    year=_year((item.get("pubdate") or "")[:4]),
                    doi=(item.get("elocationid") or "").replace("doi: ", "").replace("doi:", ""),
                )
            )
        return hits


class ZenodoService:
    async def search(self, query: str, count: int = 5) -> list[dict[str, Any]]:
        data = await fetch_json(
            "https://zenodo.org/api/records",
            params={"q": query, "size": count},
            headers=_UA,
        )
        raw = ((data.get("hits") or {}).get("hits")) or data.get("hits") or []
        hits = []
        for item in raw:
            meta = item.get("metadata") or {}
            source = item.get("_source") or {}
            meta = meta or source.get("metadata") or {}
            links = item.get("links") or {}
            doi = meta.get("doi") or item.get("doi") or ""
            page = links.get("self_html") or links.get("self") or ""
            url = page or (f"https://doi.org/{doi}" if doi else "")
            hits.append(
                make_hit(
                    title=_text(meta.get("title")),
                    url=url,
                    query=query,
                    source="zenodo",
                    snippet=_text(meta.get("description")),
                    year=_year((meta.get("publication_date") or "")[:4]),
                    doi=doi,
                )
            )
        return hits


class HalService:
    async def search(self, query: str, count: int = 5) -> list[dict[str, Any]]:
        data = await fetch_json(
            "https://api.archives-ouvertes.fr/search/",
            params={
                "q": query,
                "wt": "json",
                "rows": count,
                "fl": "title_s,uri_s,abstract_s,doiId_s,producedDateY_i",
            },
            headers=_UA,
        )
        hits = []
        for doc in ((data.get("response") or {}).get("docs")) or []:
            hits.append(
                make_hit(
                    title=_text(doc.get("title_s")),
                    url=_text(doc.get("uri_s")),
                    query=query,
                    source="hal",
                    snippet=_text(doc.get("abstract_s")),
                    year=_year(doc.get("producedDateY_i")),
                    doi=_text(doc.get("doiId_s")),
                )
            )
        return hits


class DoajService:
    async def search(self, query: str, count: int = 5) -> list[dict[str, Any]]:
        safe_q = quote(query.replace("/", " "), safe="")
        data = await fetch_json(
            f"https://doaj.org/api/search/articles/{safe_q}",
            params={"pageSize": count},
            headers=_UA,
        )
        hits = []
        for item in data.get("results") or []:
            bib = item.get("bibjson") or {}
            links = bib.get("link") or []
            url = ""
            if isinstance(links, list) and links:
                url = links[0].get("url") or ""
            doi = ""
            for ident in bib.get("identifier") or []:
                if isinstance(ident, dict) and str(ident.get("type") or "").lower() == "doi":
                    doi = ident.get("id") or ""
                    break
            hits.append(
                make_hit(
                    title=_text(bib.get("title")),
                    url=url,
                    query=query,
                    source="doaj",
                    snippet=_text(bib.get("abstract")),
                    year=_year(bib.get("year")),
                    doi=doi,
                )
            )
        return hits


class Plugin:
    id = "search.oa"
    provides = [
        "search_crossref",
        "search_dblp",
        "search_openreview",
        "search_eupmc",
        "search_pubmed",
        "search_zenodo",
        "search_hal",
        "search_doaj",
    ]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("search_crossref", CrossrefService())
        ctx.provide("search_dblp", DblpService())
        ctx.provide("search_openreview", OpenReviewService())
        ctx.provide("search_eupmc", EuropePmcService())
        ctx.provide("search_pubmed", PubmedService())
        ctx.provide("search_zenodo", ZenodoService())
        ctx.provide("search_hal", HalService())
        ctx.provide("search_doaj", DoajService())
