"""Shared search helpers.

Fetched pages are untrusted data. Full text is downloaded only from an
allowlist so a paper or a redirect cannot point the agent at an internal host.
"""

from __future__ import annotations

import html
import io
import ipaddress
import re
import zlib
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from openrd.settings import settings
from openrd.util.canon import (
    canon_query,
    canon_url,
    extract_arxiv_id,
    normalize_doi,
    paper_key,
)
from openrd.util.text import tokenize

# Metadata APIs. Not a browsing proxy.
API_HOSTS = frozenset(
    {
        "export.arxiv.org",
        "api.semanticscholar.org",
        "api.openalex.org",
        "api.github.com",
        "api.crossref.org",
        "dblp.org",
        "api2.openreview.net",
        "www.ebi.ac.uk",
        "eutils.ncbi.nlm.nih.gov",
        "zenodo.org",
        "api.archives-ouvertes.fr",
        "doaj.org",
    }
)

# Hosts the agent may download a paper from, on its own behalf.
FULLTEXT_HOSTS = frozenset(
    {
        "export.arxiv.org",
        "arxiv.org",
        "ar5iv.org",
        "ar5iv.labs.arxiv.org",
        "openreview.net",
        "www.ebi.ac.uk",
        "europepmc.org",
        "www.ncbi.nlm.nih.gov",
        "eutils.ncbi.nlm.nih.gov",
    }
)

_INJECT = re.compile(
    r"(ignore (all |any |previous |above |prior )?instructions"
    r"|disregard (the )?(above|prior|previous)"
    r"|you are now"
    r"|system prompt"
    r"|do not tell the user"
    r"|<\s*/?\s*(system|im_start|im_end)\s*>"
    r"|reveal (your |the )?(system |hidden )?prompt"
    r"|exfiltrate|override (the )?(system|developer))",
    re.I,
)
_ROLE_LINE = re.compile(r"^\s*(system|assistant|developer|tool)\s*:", re.I)
_DROP_BLOCKS = re.compile(
    r"(?is)<(script|style|noscript|template|iframe|object)\b[^>]*>.*?</\1>|<!--.*?-->"
)
_TAG = re.compile(r"(?s)<[^>]+>")
_WS = re.compile(r"[ \t]+\n|\n{3,}")

_MEDICAL = re.compile(
    r"\b(clinical|patient|disease|pubmed|cancer|genome|protein|trial|diagnos)\w*",
    re.I,
)

SOURCE_POOL: dict[str, tuple[str, ...]] = {
    "papers": (
        "search_arxiv",
        "search_s2",
        "search_openalex",
        "search_crossref",
        "search_dblp",
        "search_openreview",
        "search_eupmc",
        "search_hal",
        "search_doaj",
    ),
    "method": (
        "search_arxiv",
        "search_s2",
        "search_openalex",
        "search_crossref",
        "search_dblp",
        "search_openreview",
        "search_eupmc",
        "search_hal",
    ),
    "domain": (
        "search_arxiv",
        "search_openalex",
        "search_s2",
        "search_crossref",
        "search_eupmc",
        "search_doaj",
        "search_hal",
    ),
    "negative": (
        "search_arxiv",
        "search_s2",
        "search_openalex",
        "search_web",
        "search_crossref",
    ),
    "code": ("search_github", "search_web", "search_zenodo"),
    "data": ("search_zenodo", "search_openalex", "search_eupmc", "search_github", "search_doaj"),
    "fallback": (
        "search_arxiv",
        "search_s2",
        "search_openalex",
        "search_crossref",
        "search_dblp",
    ),
}


class FetchDenied(Exception):
    """URL or body is not safe to download."""


def scrub_injection(text: str) -> str:
    """Drop instruction-shaped lines. Do not return the original attack text."""
    if not text:
        return ""
    cleaned = _INJECT.sub("[filtered]", text)
    lines = []
    for line in cleaned.splitlines():
        if _ROLE_LINE.match(line) or _INJECT.search(line):
            lines.append("[filtered]")
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def html_to_text(raw: str) -> str:
    without = _DROP_BLOCKS.sub(" ", raw or "")
    text = _TAG.sub(" ", without)
    text = html.unescape(text)
    text = _WS.sub("\n", text)
    return scrub_injection(text)


def fence_untrusted(text: str, source: str, limit: int = 900) -> str:
    body = scrub_injection(text or "")[:limit]
    ref = scrub_injection(source)[:120].replace('"', "")
    return f'<untrusted_source ref="{ref}">\n{body}\n</untrusted_source>'


def extractive_card(text: str, focus: str, *, source: str, limit: int | None = None) -> str:
    """Keep a few sentences that overlap the goal. The rest stays off the prompt."""
    cap = limit or settings.paper_card_chars
    clean = html_to_text(text) if "<" in (text or "") else scrub_injection(text or "")
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", clean) if p.strip()]
    focus_toks = set(tokenize(focus))
    ranked: list[tuple[int, int, str]] = []
    for i, sent in enumerate(parts):
        if len(sent) < 40:
            continue
        overlap = len(set(tokenize(sent)) & focus_toks)
        ranked.append((overlap, i, sent))
    if not ranked:
        body = clean[:cap]
    else:
        top = sorted(ranked, key=lambda item: (item[0], -item[1]), reverse=True)[:5]
        body = " ".join(sent for _, _, sent in sorted(top, key=lambda item: item[1]))[:cap]
    return fence_untrusted(body, source, limit=cap)


def host_allowed(host: str, hosts: frozenset[str]) -> bool:
    name = (host or "").lower().rstrip(".")
    if not name:
        return False
    if name in hosts:
        return True
    return any(name.endswith("." + item) for item in hosts)


def vet_url(url: str, *, hosts: frozenset[str] = FULLTEXT_HOSTS) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"https", "http"}:
        raise FetchDenied("scheme")
    if parsed.username or parsed.password:
        raise FetchDenied("credentials in url")
    host = (parsed.hostname or "").lower().rstrip(".")
    local_names = {"localhost", "metadata.google.internal"}
    blocked = host in local_names or host.endswith((".local", ".internal"))
    if not host or blocked:
        raise FetchDenied("host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise FetchDenied("raw ip")
    if parsed.port and parsed.port not in {80, 443}:
        raise FetchDenied("port")
    if not host_allowed(host, hosts):
        raise FetchDenied("not allowlisted")
    path = parsed.path or "/"
    netloc = host if parsed.port is None else parsed.netloc.lower()
    return urlunparse((parsed.scheme, netloc, path, "", parsed.query, ""))


def _pdf_to_text(data: bytes, max_pages: int = 6) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        raise FetchDenied("pdf needs pypdf") from exc
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages[:max_pages]:
        pages.append(page.extract_text() or "")
    return scrub_injection("\n".join(pages))


async def fetch_text(
    url: str,
    *,
    hosts: frozenset[str] = FULLTEXT_HOSTS,
    max_bytes: int = 1_500_000,
    timeout: float = 25,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Download text from an allowlisted host. Redirects are checked one by one."""
    current = vet_url(url, hosts=hosts)
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
    assert client is not None
    try:
        for _ in range(4):
            async with client.stream(
                "GET",
                current,
                headers={"User-Agent": "OpenRD/0.1 (local research; untrusted content)"},
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    loc = response.headers.get("location")
                    if not loc:
                        raise FetchDenied("redirect")
                    current = vet_url(urljoin(current, loc), hosts=hosts)
                    continue
                response.raise_for_status()
                ctype = (response.headers.get("content-type") or "").lower()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        break
                    chunks.append(chunk)
                data = b"".join(chunks)
            if "pdf" in ctype or data.startswith(b"%PDF"):
                return _pdf_to_text(data)[: settings.paper_disk_chars]
            allowed_types = ("html", "xml", "text", "json", "plain")
            if ctype and not any(token in ctype for token in allowed_types):
                raise FetchDenied("content-type")
            text = data.decode("utf-8", errors="replace")
            if "html" in ctype or "xml" in ctype or text.lstrip().startswith("<"):
                text = html_to_text(text)
            else:
                text = scrub_injection(text)
            return text[: settings.paper_disk_chars]
        raise FetchDenied("too many redirects")
    finally:
        if own_client:
            await client.aclose()


async def fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: float = 30,
    headers: dict[str, str] | None = None,
) -> Any:
    safe = vet_url(url, hosts=API_HOSTS)
    hdrs = {"User-Agent": "OpenRD/0.1 (mailto:openrd@localhost)"}
    if headers:
        hdrs.update(headers)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.get(safe, params=params, headers=hdrs)
        if response.status_code in {301, 302, 303, 307, 308}:
            loc = response.headers.get("location")
            if not loc:
                raise FetchDenied("redirect")
            nxt = vet_url(urljoin(safe, loc), hosts=API_HOSTS)
            response = await client.get(nxt, headers=hdrs)
        response.raise_for_status()
        return response.json()


def make_hit(
    *,
    title: str,
    url: str,
    query: str,
    source: str,
    snippet: str = "",
    pdf: str | None = None,
    year: int | None = None,
    citations: int = 0,
    doi: str | None = None,
    arxiv_id: str | None = None,
    pmcid: str | None = None,
    openreview_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    aid = (arxiv_id or extract_arxiv_id(url) or extract_arxiv_id(pdf or "")).lower()
    aid = re.sub(r"v\d+$", "", aid)
    doi_n = normalize_doi(doi or "") or normalize_doi(url)
    hit: dict[str, Any] = {
        "title": scrub_injection(re.sub(r"\s+", " ", title or "")).strip()[:300],
        "url": url or "",
        "url_canon": canon_url(url or ""),
        "snippet": scrub_injection(snippet or "")[:800],
        "pdf": pdf,
        "year": year,
        "citations": int(citations or 0),
        "source": source,
        "query_canon": canon_query(query),
        "doi": doi_n or None,
        "arxiv_id": aid or None,
        "pmcid": (pmcid or "").upper() or None,
        "openreview_id": openreview_id or None,
        "paper_key": paper_key(
            url=url or "",
            doi=doi_n,
            arxiv_id=aid,
            pmcid=pmcid or "",
            openreview_id=openreview_id or "",
            pdf=pdf or "",
        ),
    }
    for key, value in extra.items():
        scalar = value is None or isinstance(value, (str, int, float, bool))
        if key not in hit and scalar:
            hit[key] = value
    return hit


def sources_for_intent(intent: str, query: str, available: set[str]) -> list[str]:
    names = SOURCE_POOL.get(intent or "papers", SOURCE_POOL["papers"])
    pool = [name for name in names if name in available]
    if not pool:
        pool = [name for name in SOURCE_POOL["fallback"] if name in available]
    if not pool:
        return []
    fanout = max(1, settings.source_fanout)
    start = zlib.crc32(canon_query(query).encode()) % len(pool)
    chosen: list[str] = []
    for offset in range(min(fanout, len(pool))):
        name = pool[(start + offset) % len(pool)]
        if name not in chosen:
            chosen.append(name)
    if _MEDICAL.search(query or "") and "search_pubmed" in available:
        if "search_pubmed" not in chosen:
            chosen.append("search_pubmed")
    return chosen


