from __future__ import annotations

from typing import Any

from openrd.core.context import Context
from openrd.db.store import get_store
from openrd.util.canon import canon_query, canon_url
from openrd.util.embed import cosine
from openrd.util.text import bm25_scores


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
        embedding = self.embed.embed(f"{title}\n{body}") if self.embed else None
        return self.store.add_archive(
            {
                "project_id": self.project_id,
                "kind": kind,
                "title": title,
                "body": body,
                "url": url,
                "url_canon": url_canon,
                "query_canon": query_canon,
                "embedding": embedding,
                "meta": {k: v for k, v in meta.items() if k not in ("url", "query")},
            }
        )

    def seen_url(self, url: str) -> bool:
        assert self.project_id
        return self.store.find_archive_url(self.project_id, canon_url(url)) is not None

    def seen_query(self, query: str) -> bool:
        assert self.project_id
        return self.store.find_archive_query(self.project_id, canon_query(query)) is not None

    def search(self, query: str, k: int = 8, kind: str | None = None) -> list[dict[str, Any]]:
        assert self.project_id
        docs = self.store.list_archive(self.project_id, kind=kind)
        if not docs:
            return []
        bm25 = {did: s for did, s in bm25_scores(query, ((d["id"], f"{d['title']}\n{d['body']}") for d in docs))}
        qvec = self.embed.embed(query) if self.embed else None
        scored = []
        for d in docs:
            b = bm25.get(d["id"], 0.0)
            c = cosine(qvec, d.get("embedding")) if qvec is not None else 0.0
            scored.append((0.55 * b + 0.45 * c * 10, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, d in scored[:k]:
            item = dict(d)
            item["score"] = score
            item.pop("embedding", None)
            out.append(item)
        return out

    def similar_mechanism(self, text: str, threshold: float) -> dict[str, Any] | None:
        assert self.project_id and self.embed
        vec = self.embed.embed(text)
        best = None
        best_s = threshold
        for d in self.store.iter_archive_with_embeddings(self.project_id):
            if d["kind"] not in ("hypothesis", "cemetery", "mechanism"):
                continue
            s = cosine(vec, d.get("embedding"))
            if s >= best_s:
                best_s = s
                best = {**d, "similarity": s}
                best.pop("embedding", None)
        return best


class Plugin:
    id = "memory.archive"
    provides = ["archive"]
    requires = ["embed"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("archive", ArchiveService())
