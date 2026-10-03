"""Store uploaded files by role, convert to markdown cards, never dump binaries into prompts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openrd.db.store import Store
from openrd.plugins.search_common import extractive_card
from openrd.util.canon import fingerprint_text

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"}
ROLE_DIRS = {"input": "inputs", "output": "outputs", "extra": "extras"}


def role_dir(workspace: Path, role: str) -> Path:
    name = ROLE_DIRS.get(role, "extras")
    dest = workspace / name
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def ingest_upload(
    store: Store,
    *,
    project_id: str,
    workspace: Path,
    filename: str,
    data: bytes,
    mime: str | None,
    role: str = "extra",
    prompt: str = "",
    ingest_svc: Any | None = None,
    archive: Any | None = None,
) -> dict[str, Any]:
    role = role if role in ROLE_DIRS else "extra"
    dest_dir = role_dir(workspace, role)
    safe_name = Path(filename or "upload.bin").name or "upload.bin"
    dest = dest_dir / safe_name
    dest.write_bytes(data)
    rec = store.add_artifact(
        {
            "project_id": project_id,
            "filename": dest.name,
            "path": str(dest),
            "mime": mime,
            "role": role,
            "prompt": prompt or "",
            "status": "stored",
        }
    )
    project = store.get_project(project_id) or {}
    focus = f"{project.get('prompt') or ''} {project.get('goal') or ''}"
    suffix = dest.suffix.lower()
    parsed: dict[str, Any] = {"chunks": [], "claims": [], "preview": ""}
    card = ""
    if ingest_svc is not None:
        parsed = ingest_svc.ingest_path(dest)
        text = "\n".join(parsed.get("chunks") or []) or parsed.get("preview") or ""
        if suffix in IMAGE_EXT and len(text.strip()) < 40:
            card = extractive_card(
                "Image input. Transcribe or decipher via the provider vision role. "
                "Binary is not sent to the language model.",
                focus,
                source=dest.name,
                limit=400,
            )
        else:
            card = extractive_card(text or dest.name, focus, source=dest.name)
        if archive is not None and card:
            archive.add("paper_card", dest.name, card, url=str(dest))
            for i, chunk in enumerate((parsed.get("chunks") or [])[:4]):
                archive.add("note", f"{dest.name}#{i}", chunk[:800], url=str(dest))
    rec["card"] = card
    rec["parsed"] = {
        "chunks": len(parsed.get("chunks") or []),
        "claims": parsed.get("claims") or [],
    }
    hyp = None
    if role == "extra" and prompt.strip():
        fp = fingerprint_text(prompt, dest.name)
        node = store.add_tree_node(
            {
                "project_id": project_id,
                "kind": "hypothesis",
                "title": prompt.strip()[:120],
                "summary": f"{prompt.strip()}\nFile: {dest.name}",
                "status": "queued",
                "payload": {"source": dest.name, "role": "extra"},
            }
        )
        hyp = store.add_hypothesis(
            {
                "project_id": project_id,
                "line_id": "user-extra",
                "type": "explore",
                "mechanism": prompt.strip()[:200],
                "fingerprint": fp,
                "text": f"{prompt.strip()}\nFile: {dest.name}",
                "status": "queued",
                "node_id": node["id"],
            }
        )
        rec["hypothesis_id"] = hyp["id"]
        rec["node_id"] = node["id"]
        store.update_artifact(rec["id"], status="queued")
    else:
        store.update_artifact(rec["id"], status="ingested")
        rec["status"] = "queued" if hyp else "ingested"
    if hyp:
        rec["status"] = "queued"
    return rec
