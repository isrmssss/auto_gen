from __future__ import annotations

from typing import Any

from openrd.core.context import Context
from openrd.db.store import get_store
from openrd.settings import settings
from openrd.util.canon import canon_query, canon_url, query_signature
from openrd.util.embed import cosine
from openrd.util.text import bm25_scores

# Snippets and cards only. Full papers stay on disk and out of this index.
RECALL_KINDS = ("paper_card", "paper", "note", "lesson")
MECH_KINDS = ("hypothesis", "cemetery", "mechanism")


class ArchiveService:
    def __init__(self) -> None:
        self.store = get_store()
        self.project_id: str | None = None
        self.embed = None

    def bind(self, project_id: str, embed: Any) -> None:
        self.project_id = project_id
        self.embed = embed

    def add(self, kind: str, title: str, body: str, **meta: Any) -> dict[str, Any]:
        assert self.project_id
        url = meta.get("url")
        url_canon = canon_url(url) if url else None
        query = meta.get("query")
        query_canon = canon_query(query) if query else None
        clipped = (body or "")[: settings.archive_body_chars]
        embed_text = f"{title}\n{clipped}".strip()
        embedding = None
        if self.embed and embed_text and kind != "search":
            embedding = self.embed.embed(embed_text)
        return self.store.add_archive(
            {
                "project_id": self.project_id,
                "kind": kind,
                "title": (title or "")[:300],
                "body": clipped,
                "url": url,
                "url_canon": url_canon,
                "query_canon": query_canon,
                "embedding": embedding,
                "meta": {k: v for k, v in meta.items() if k not in ("url", "query")},
            }
        )

    def remember(self, kind: str, key: str, title: str = "", note: str = "") -> bool:
        assert self.project_id
        return self.store.remember_key(self.project_id, kind, key, title=title, note=note)

    def known(self, kind: str, key: str) -> bool:
        assert self.project_id
        return self.store.known_key(self.project_id, kind, key)

    def seen_url(self, url: str) -> bool:
        assert self.project_id
        return self.store.find_archive_url(self.project_id, canon_url(url)) is not None

    def seen_query(self, query: str) -> bool:
        assert self.project_id
        if self.known("query_sig", query_signature(query)):
            return True
        return self.store.find_archive_query(self.project_id, canon_query(query)) is not None

    def claim_query(self, query: str) -> bool:
        """True only the first time this query (or a rephrase) is attempted."""
        if self.seen_query(query):
            return False
        return self.remember("query_sig", query_signature(query), title=canon_query(query)[:180])

    def digest(self, limit: int = 8) -> str:
        """Short index for the planner. Titles only, never paper bodies."""
        assert self.project_id
        counts = self.store.recall_counts(self.project_id)
        recent = self.store.recent_recall(self.project_id, limit)
        bits = [f"{kind}={count}" for kind, count in sorted(counts.items()) if count]
        lines = ["Already tried (do not repeat): " + (", ".join(bits) or "nothing yet")]
        for row in recent:
            title = (row.get("title") or row.get("key") or "")[:100]
            lines.append(f"- {row['kind']}: {title}")
        return "\n".join(lines)

    def search(self, query: str, k: int = 8, kind: str | None = None) -> list[dict[str, Any]]:
        assert self.project_id
        if kind:
            docs = self.store.list_archive_kinds(self.project_id, [kind], limit=80)
        else:
            docs = self.store.list_archive_kinds(self.project_id, list(RECALL_KINDS), limit=80)
        if not docs:
            return []
        pairs = ((d["id"], f"{d['title']}\n{d['body']}") for d in docs)
        bm25 = {did: score for did, score in bm25_scores(query, pairs)}
        qvec = self.embed.embed(query) if self.embed else None
        scored = []
        for doc in docs:
            lexical = bm25.get(doc["id"], 0.0)
            semantic = cosine(qvec, doc.get("embedding")) if qvec is not None else 0.0
            bonus = 0.4 if doc.get("kind") == "paper_card" else 0.0
            scored.append((0.55 * lexical + 0.45 * semantic * 10 + bonus, doc))
        scored.sort(key=lambda item: item[0], reverse=True)
        out = []
        for score, doc in scored[:k]:
            item = dict(doc)
            item["score"] = score
            item.pop("embedding", None)
            out.append(item)
        return out

    def similar_mechanism(self, text: str, threshold: float) -> dict[str, Any] | None:
        assert self.project_id and self.embed
        vec = self.embed.embed(text)
        best = None
        best_s = threshold
        for doc in self.store.iter_archive_with_embeddings(self.project_id, MECH_KINDS):
            score = cosine(vec, doc.get("embedding"))
            if score >= best_s:
                best_s = score
                best = {**doc, "similarity": score}
                best.pop("embedding", None)
        return best


class Plugin:
    id = "memory.archive"
    provides = ["archive"]
    requires = ["embed"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("archive", ArchiveService())
