from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
}


def canon_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING
    ]
    query.sort()
    return urlunparse((scheme, netloc, path, "", urlencode(query), ""))


_WS = re.compile(r"\s+")


def canon_query(query: str) -> str:
    q = _WS.sub(" ", (query or "").strip().lower())
    return q


def fingerprint_text(*parts: str) -> str:
    blob = "\n".join(p.strip().lower() for p in parts if p)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def mechanism_key(mechanism: str) -> str:
    return canon_query(mechanism)


_ARXIV_URL = re.compile(
    r"(?:arxiv\.org|ar5iv\.org|ar5iv\.labs\.arxiv\.org)/(?:abs|pdf|html|src|ftp)/([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?",
    re.I,
)
_DOI = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_STOP = frozenset(
    """
    the a an of and or to for in on with without from by at as is are was were be
    this that these those how why what when where which into over under vs versus
    using use used paper papers method methods approach review survey recent
    state art sota via than then into about across
    """.split()
)


def extract_arxiv_id(value: str) -> str:
    match = _ARXIV_URL.search(value or "")
    return match.group(1) if match else ""


def normalize_doi(value: str) -> str:
    raw = (value or "").strip()
    raw = re.sub(r"^https?://(dx\.)?doi\.org/", "", raw, flags=re.I)
    match = _DOI.search(raw)
    return match.group(0).lower().rstrip(".") if match else ""


def paper_key(
    url: str = "",
    doi: str = "",
    arxiv_id: str = "",
    pmcid: str = "",
    openreview_id: str = "",
    pdf: str = "",
) -> str:
    aid = (arxiv_id or "").strip().lower()
    aid = re.sub(r"v\d+$", "", aid)
    if not aid:
        aid = extract_arxiv_id(url) or extract_arxiv_id(pdf)
    if aid:
        return f"arxiv:{aid}"
    doi_n = normalize_doi(doi) or normalize_doi(url)
    if doi_n:
        return f"doi:{doi_n}"
    pmc = (pmcid or "").strip().upper()
    if pmc:
        return f"pmc:{pmc}"
    oid = (openreview_id or "").strip()
    if oid:
        return f"openreview:{oid}"
    canon = canon_url(url)
    return f"url:{canon}" if canon else ""


def query_signature(query: str) -> str:
    """Order-insensitive token key so rephrased queries count as the same attempt."""
    tokens = sorted({t for t in re.findall(r"[a-z0-9]{3,}", canon_query(query)) if t not in _STOP})
    if not tokens:
        return canon_query(query)
    return fingerprint_text(" ".join(tokens))
