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
