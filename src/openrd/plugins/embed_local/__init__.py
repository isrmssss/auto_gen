from __future__ import annotations

from openrd.core.context import Context
from openrd.util.embed import cosine, hashing_embed


class EmbedService:
    def embed(self, text: str) -> bytes:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            model = getattr(self, "_st", None)
            if model is None:
                model = SentenceTransformer("all-MiniLM-L6-v2")
                self._st = model
            vec = model.encode([text or ""], normalize_embeddings=True)[0]
            return vec.astype("float32").tobytes()
        except Exception:
            return hashing_embed(text)

    def similarity(self, a: bytes, b: bytes) -> float:
        return cosine(a, b)


class Plugin:
    id = "embed.local"
    provides = ["embed"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("embed", EmbedService())
