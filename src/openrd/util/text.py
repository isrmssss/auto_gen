from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any, Iterable

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


def extract_json(text: str) -> Any:
    if not text:
        raise ValueError("empty model output")
    text = text.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def clip_tokens(text: str, budget: int) -> str:
    if not text:
        return ""
    max_chars = max(32, budget * 4)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n…[truncated]"


_TOKEN = re.compile(r"[a-z0-9а-яё]+", re.I)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def bm25_scores(query: str, docs: Iterable[tuple[str, str]], k1: float = 1.5, b: float = 0.75) -> list[tuple[str, float]]:
    corpus = [(doc_id, tokenize(body)) for doc_id, body in docs]
    if not corpus:
        return []
    avgdl = sum(len(toks) for _, toks in corpus) / max(1, len(corpus))
    df: Counter[str] = Counter()
    for _, toks in corpus:
        df.update(set(toks))
    n = len(corpus)
    qtoks = tokenize(query)
    scores: list[tuple[str, float]] = []
    for doc_id, toks in corpus:
        tf = Counter(toks)
        dl = len(toks) or 1
        score = 0.0
        for t in qtoks:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            denom = tf[t] + k1 * (1 - b + b * dl / avgdl)
            score += idf * (tf[t] * (k1 + 1)) / denom
        scores.append((doc_id, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores
