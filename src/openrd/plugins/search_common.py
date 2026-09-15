from __future__ import annotations

from typing import Any

import httpx

from openrd.settings import settings


def scrub_injection(text: str) -> str:
    lowered = text.lower()
    markers = (
        "ignore previous instructions",
        "ignore all instructions",
        "you are now",
        "system prompt",
        "disregard the above",
    )
    if any(m in lowered for m in markers):
        return "[scrubbed untrusted content]\n" + text[:500]
    return text


async def fetch_json(url: str, params: dict[str, Any] | None = None, timeout: float = 30) -> Any:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()
