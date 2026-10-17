"""Store uploaded files by role, convert to markdown cards, never dump binaries into prompts."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from openrd.db.store import Store
from openrd.plugins.rnd_quality_bar import expand_writeup
from openrd.plugins.search_common import extractive_card
from openrd.util.canon import fingerprint_text

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"}
TABLE_EXT = {".csv", ".tsv"}
ROLE_DIRS = {"input": "inputs", "output": "outputs", "extra": "extras"}
_TARGET_NAMES = {"target", "label", "labels", "y", "outcome", "response"}


def _merge_data_card(store: Store, project_id: str, block: str) -> None:
    block = block.strip()
    if not block:
        return
    prev = (store.get_memory(project_id).get("data_card") or "").strip()
    if block in prev:
        return
    store.patch_memory(project_id, "data_card", f"{prev}\n{block}".strip() if prev else block)


def _cell_kind(value: str) -> str:
    text = value.strip()
    if not text:
        return "empty"
    try:
        int(text)
        return "int"
    except ValueError:
        pass
    try:
        float(text)
        return "float"
    except ValueError:
        return "str"


def profile_table(name: str, data: bytes, metric: str, delimiter: str = ",") -> str:
    sample = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(sample), delimiter=delimiter)
    rows = []
    for i, row in enumerate(reader):
        if i > 40:
            break
        if any(cell.strip() for cell in row):
            rows.append(row)
    if not rows:
        return f"{name}: empty table. metric={metric}."
    header = [cell.strip() or f"col{i}" for i, cell in enumerate(rows[0])]
    body = rows[1:]
    lines = [line for line in sample.splitlines() if line.strip()]
    data_rows = max(0, len(lines) - 1)
    kinds: list[str] = []
    for idx, col in enumerate(header):
        seen = [_cell_kind(row[idx]) for row in body[:20] if idx < len(row)]
        seen = [k for k in seen if k != "empty"]
        kinds.append(f"{col}:{seen[0] if seen else 'unknown'}")
    lowered = {col.lower(): col for col in header}
    target = next((lowered[n] for n in _TARGET_NAMES if n in lowered), header[-1])
    return (
        f"{name}: rows={data_rows} columns={','.join(header)}. "
        f"types={','.join(kinds)}. target_candidate={target}. metric={metric}."
    )


def profile_image(name: str, suffix: str) -> str:
    return (
        f"{name}: image {suffix or 'unknown'}. "
        "Needs the provider vision role. Binary is not sent to the model."
    )


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
    metric = str((project.get("kpi") or {}).get("primary") or "primary")
    if suffix in TABLE_EXT or (mime or "").split(";")[0].strip() == "text/csv":
        delim = "\t" if suffix == ".tsv" else ","
        _merge_data_card(store, project_id, profile_table(dest.name, data, metric, delim))
    elif suffix in IMAGE_EXT:
        _merge_data_card(store, project_id, profile_image(dest.name, suffix))
    hyp = None
    if role == "extra" and prompt.strip():
        mechanism = prompt.strip()[:200]
        text = expand_writeup(mechanism, f"{prompt.strip()}\nFile: {dest.name}", metric)
        fp = fingerprint_text(prompt, dest.name)
        node = store.add_tree_node(
            {
                "project_id": project_id,
                "kind": "hypothesis",
                "title": prompt.strip()[:120],
                "summary": text,
                "status": "queued",
                "payload": {"source": dest.name, "role": "extra"},
            }
        )
        hyp = store.add_hypothesis(
            {
                "project_id": project_id,
                "line_id": "user-extra",
                "type": "explore",
                "mechanism": mechanism,
                "fingerprint": fp,
                "text": text,
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
