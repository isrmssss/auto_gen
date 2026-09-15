from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openrd.core.context import Context


def _chunk_markdown(text: str, max_chars: int = 4000) -> list[str]:
    parts = re.split(r"\n(?=#{1,3} )", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        if len(buf) + len(part) > max_chars and buf:
            chunks.append(buf.strip())
            buf = part
        else:
            buf += ("\n" if buf else "") + part
    if buf.strip():
        chunks.append(buf.strip())
    return chunks or [text[:max_chars]]


def _read_fallback(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".csv"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return f"(unreadable PDF {path.name}; install docling or pypdf)"
    try:
        from docling.document_converter import DocumentConverter  # type: ignore

        conv = DocumentConverter()
        doc = conv.convert(str(path))
        return doc.document.export_to_markdown()
    except Exception:
        return path.read_text(encoding="utf-8", errors="replace")[:50_000]


CLAIM_RE = re.compile(r"(?im)^(?:[-*] |\d+\. )?(?:we |this paper |the method |hypothesis |claim[: ]).*")


class IngestService:
    def ingest_path(self, path: Path) -> dict[str, Any]:
        text = _read_fallback(path)
        chunks = _chunk_markdown(text)
        claims: list[str] = []
        for ch in chunks:
            claims.extend(m.group(0).strip() for m in CLAIM_RE.finditer(ch))
            if "propose" in ch.lower() or "we introduce" in ch.lower():
                claims.append(ch[:280])
        return {
            "path": str(path),
            "chars": len(text),
            "chunks": chunks,
            "claims": claims[:40],
            "preview": text[:1500],
        }


class Plugin:
    id = "ingest.docling"
    provides = ["ingest"]
    requires = ["archive"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("ingest", IngestService())
