from __future__ import annotations

from typing import Any

from openrd.core.context import Context
from openrd.core.loader import llm_plugin_catalog
from openrd.db.store import get_store
from openrd.settings import settings
from openrd.util.text import clip_tokens


class Compiler:
    def __init__(self) -> None:
        self.store = get_store()
        self.ctx: Context | None = None
        self.project_id: str | None = None

    def bind(self, ctx: Context, project_id: str) -> None:
        self.ctx = ctx
        self.project_id = project_id

    def brief(self, phase: str, extra: str = "") -> str:
        assert self.ctx and self.project_id
        core = self.ctx.require("memory_core").render()
        archive = self.ctx.require("archive")
        similar = archive.search(f"{phase} {extra}", k=5) if extra else archive.search(phase, k=5)
        sim_lines = []
        for d in similar:
            sim_lines.append(f"- [{d['kind']}] {d.get('title')}: {str(d.get('body') or '')[:240]}")
        hyps = self.store.list_hypotheses(self.project_id)[-8:]
        hyp_lines = [
            f"- {h['id']} {h['type']} {h['status']} :: {h['mechanism'][:120]}" for h in hyps
        ]
        cemetery = self.store.list_cemetery(self.project_id)[-12:]
        cem_lines = [f"- {c['mechanism_class']}: {c['lesson'][:200]}" for c in cemetery]
        claims = self.store.list_claims(self.project_id)
        claim_lines = [f"- {c['claim_type']}:{c['claim_key']} by {c['owner_agent']}" for c in claims]
        events = self.store.list_events(self.project_id, after_seq=max(0, self.store.last_seq(self.project_id) - 12))
        ev_lines = [f"- #{e['seq']} {e['type']}: {str(e.get('payload'))[:180]}" for e in events]
        tools = clip_tokens(llm_plugin_catalog(self.ctx), settings.prompt_tools_token_budget)
        body = "\n".join(
            [
                f"# Phase: {phase}",
                extra,
                "# Similar archive (do not repeat)",
                "\n".join(sim_lines) or "(empty)",
                "# Recent hypotheses",
                "\n".join(hyp_lines) or "(none)",
                "# Cemetery",
                "\n".join(cem_lines) or "(none)",
                "# Blackboard claims",
                "\n".join(claim_lines) or "(none)",
                "# Last events",
                "\n".join(ev_lines) or "(none)",
            ]
        )
        compiled = "\n\n".join(
            [core, clip_tokens(body, settings.prompt_brief_token_budget), tools]
        )
        return compiled


class Plugin:
    id = "memory.compiler"
    provides = ["compiler"]
    requires = ["memory_core", "archive", "journal"]

    def apply(self, ctx: Context) -> None:
        svc = Compiler()
        svc.bind(ctx, ctx.project_id or "")
        ctx.provide("compiler", svc)
