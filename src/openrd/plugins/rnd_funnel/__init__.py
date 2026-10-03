"""Research funnel: formalize → structures → domains → methods. Heuristic first, LLM optional."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from openrd.core.context import Context
from openrd.db.store import get_store
from openrd.util.canon import fingerprint_text
from openrd.util.text import tokenize

_DECODE = re.compile(
    r"расшифр|decrypt|decipher|transcri|ocr|письм|рукопис|cipher|decode",
    re.I,
)
_NOISE = re.compile(r"noisy|noise|шум|corrupted|outlier|label.?noise", re.I)
_TABULAR = re.compile(r"rmsle|rmse|auc|kaggle|tabular|dataset|baseline|метрик", re.I)


def _catalog() -> dict[str, Any]:
    path = Path(__file__).with_name("catalog.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _overlap(text: str, terms: list[str]) -> int:
    toks = set(tokenize(text))
    hit = 0
    for term in terms:
        bits = set(tokenize(term.replace("_", " ")))
        if bits & toks or term.lower() in text.lower():
            hit += 1
    return hit


class Funnel:
    def __init__(self) -> None:
        self.store = get_store()
        self.ctx: Context | None = None
        self.project_id: str | None = None
        self.catalog = _catalog()

    def bind(self, ctx: Context, project_id: str) -> None:
        self.ctx = ctx
        self.project_id = project_id

    def _blob(self, project: dict[str, Any]) -> str:
        mem = self.store.get_memory(self.project_id) if self.project_id else {}
        arts = self.store.list_artifacts(self.project_id) if self.project_id else []
        names = " ".join(a.get("filename") or "" for a in arts)
        roles = " ".join(a.get("role") or "" for a in arts)
        return " ".join(
            [
                project.get("prompt") or "",
                project.get("goal") or "",
                mem.get("prompt") or "",
                mem.get("goal") or "",
                names,
                roles,
            ]
        )

    def is_short_path(self, project: dict[str, Any]) -> bool:
        blob = self._blob(project)
        arts = self.store.list_artifacts(self.project_id) if self.project_id else []
        has_image = any(
            Path(a.get("filename") or "").suffix.lower()
            in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
            for a in arts
            if a.get("role") == "input"
        )
        return bool(_DECODE.search(blob)) or (has_image and not _TABULAR.search(blob))

    def formalize(self, project: dict[str, Any]) -> dict[str, Any]:
        blob = self._blob(project)
        short = self.is_short_path(project)
        obj = "images" if short else ("text" if "text" in blob.lower() else "object_set")
        if _TABULAR.search(blob):
            obj = "object_set"
        task = "transcription" if short else ("regression" if _TABULAR.search(blob) else "search")
        kpi = project.get("kpi") or {}
        result = {
            "object": obj,
            "task": task,
            "short_path": short,
            "skip_math": short,
            "metric": kpi.get("primary") or "primary",
            "higher_is_better": bool(kpi.get("higher_is_better", True)),
            "baseline": "user-provided" if any(
                a.get("role") == "input" for a in (self.store.list_artifacts(self.project_id) or [])
            ) else "none",
        }
        if self.project_id:
            self.store.patch_memory(self.project_id, "formalize", str(result))
            existing = [
                n
                for n in self.store.list_tree(self.project_id)
                if n.get("kind") == "formalize"
            ]
            if not existing:
                self.store.add_tree_node(
                    {
                        "project_id": self.project_id,
                        "kind": "formalize",
                        "title": f"{obj} / {task}",
                        "status": "done",
                        "summary": "short path" if short else "research funnel",
                        "payload": result,
                    }
                )
                if not short:
                    for struct in (self.catalog.get("structures") or [])[:6]:
                        self.store.add_tree_node(
                            {
                                "project_id": self.project_id,
                                "kind": "structure",
                                "title": struct["id"],
                                "status": "open",
                                "summary": struct.get("ask") or "",
                            }
                        )
        return result

    def score_domains(self, project: dict[str, Any], top_n: int = 4) -> list[dict[str, Any]]:
        if self.is_short_path(project):
            return []
        if self.project_id:
            existing = [
                n for n in self.store.list_tree(self.project_id) if n.get("kind") == "domain"
            ]
            if existing:
                out = []
                for node in existing:
                    if node.get("title") == "cross-science analogies":
                        continue
                    payload = node.get("payload") or {
                        "id": node.get("title"),
                        "total": 0,
                        "methods": [],
                    }
                    out.append(payload)
                return out
        blob = self._blob(project)
        scored = []
        for domain in self.catalog.get("domains") or []:
            methods = domain.get("methods") or []
            hit = _overlap(blob, [domain["id"], *methods])
            structure = 8 if hit else 3
            novelty = 6
            cost = 5
            total = structure + min(10, hit * 2) + novelty
            scored.append(
                {
                    "id": domain["id"],
                    "structure": structure,
                    "developed": 7,
                    "papers": 7,
                    "code": 6,
                    "integrate": 6,
                    "novelty": novelty,
                    "compute_cost": cost,
                    "total": total,
                    "methods": methods[:5],
                }
            )
        scored.sort(key=lambda d: d["total"], reverse=True)
        top = scored[:top_n]
        if self.project_id:
            for item in top:
                self.store.add_tree_node(
                    {
                        "project_id": self.project_id,
                        "kind": "domain",
                        "title": item["id"],
                        "status": "scored",
                        "summary": f"score {item['total']}",
                        "payload": item,
                    }
                )
                for method in item["methods"][:3]:
                    self.store.add_tree_node(
                        {
                            "project_id": self.project_id,
                            "kind": "method",
                            "title": f"{item['id']}/{method}",
                            "status": "open",
                            "summary": method,
                            "payload": {"domain": item["id"], "method": method},
                        }
                    )
        return top

    def maybe_noise_job(self, project: dict[str, Any]) -> dict[str, Any] | None:
        blob = self._blob(project)
        if not _NOISE.search(blob) or not self.project_id:
            return None
        existing = [
            j for j in self.store.list_jobs(self.project_id) if j.get("kind") == "denoise"
        ]
        if existing:
            return existing[0]
        return self.store.add_job(
            {
                "project_id": self.project_id,
                "kind": "denoise",
                "title": "Reduce input noise",
                "status": "open",
                "metric": "noise_level",
                "payload": {"reason": "noisy data flagged in prompt/goal"},
            }
        )

    def mass_candidates(
        self, domains: list[dict[str, Any]], limit: int = 12
    ) -> list[dict[str, Any]]:
        """Level 12: local combinations, no LLM per pair."""
        out = []
        structs = [s["id"] for s in (self.catalog.get("structures") or [])[:8]]
        for domain in domains:
            for method in (domain.get("methods") or [])[:4]:
                for struct in structs[:2]:
                    out.append(
                        {
                            "domain": domain["id"],
                            "method": method,
                            "structure": struct,
                            "hypothesis": f"{method} on {struct} for the stated task",
                        }
                    )
                    if len(out) >= limit:
                        return out
        return out

    def seed_hypotheses(
        self, project: dict[str, Any], domains: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        assert self.project_id
        if self.is_short_path(project):
            text = (
                "Transcribe the input image/document into correct Russian text "
                "and verify against the goal."
            )
            fp = fingerprint_text("transcribe", text)
            if self.store.has_hypothesis_fingerprint(self.project_id, fp):
                return []
            rec = self.store.add_hypothesis(
                {
                    "project_id": self.project_id,
                    "line_id": "decode",
                    "type": "validate",
                    "mechanism": "vision transcription plus language check",
                    "fingerprint": fp,
                    "text": text,
                    "status": "queued",
                }
            )
            self.store.add_tree_node(
                {
                    "project_id": self.project_id,
                    "kind": "hypothesis",
                    "title": rec["mechanism"],
                    "status": "queued",
                    "summary": text,
                    "payload": rec,
                }
            )
            return [rec]
        created = []
        for cand in self.mass_candidates(domains, limit=6):
            fp = fingerprint_text(cand["method"], cand["structure"])
            if self.store.has_hypothesis_fingerprint(self.project_id, fp):
                continue
            rec = self.store.add_hypothesis(
                {
                    "project_id": self.project_id,
                    "line_id": cand["domain"],
                    "type": "explore",
                    "mechanism": f"{cand['method']}+{cand['structure']}",
                    "fingerprint": fp,
                    "text": cand["hypothesis"],
                    "status": "queued",
                }
            )
            self.store.add_tree_node(
                {
                    "project_id": self.project_id,
                    "kind": "hypothesis",
                    "title": rec["mechanism"],
                    "status": "queued",
                    "summary": cand["hypothesis"],
                    "payload": rec,
                }
            )
            created.append(rec)
        return created


class Plugin:
    id = "rnd.funnel"
    provides = ["funnel"]
    requires: list[str] = ["memory_core"]

    def apply(self, ctx: Context) -> None:
        svc = Funnel()
        svc.bind(ctx, ctx.project_id or "")
        ctx.provide("funnel", svc)
