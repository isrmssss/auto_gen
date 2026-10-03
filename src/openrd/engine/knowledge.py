"""Project knowledge/ markdown projection — files are a view, not source of truth."""

from __future__ import annotations

from pathlib import Path

from openrd.db.store import Store


def export_knowledge(store: Store, project_id: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    project = store.get_project(project_id) or {}
    mem = store.get_memory(project_id)
    hyps = store.list_hypotheses(project_id)
    cemetery = store.list_cemetery(project_id)
    runs = store.list_runs(project_id)

    (dest / "CONTEXT.md").write_text(
        "# CONTEXT\n\n"
        f"## Goal\n\n{mem.get('goal') or project.get('goal') or ''}\n\n"
        f"## Champion\n\n{mem.get('champion') or '(none)'}\n\n"
        f"## Open questions\n\n{mem.get('open_questions') or ''}\n\n"
        f"## Bans\n\n{mem.get('bans') or ''}\n\n"
        f"## Budget\n\n{mem.get('budget') or ''}\n",
        encoding="utf-8",
    )
    (dest / "METRICS.md").write_text(
        "# METRICS\n\n```json\n" + (mem.get("kpi") or "{}") + "\n```\n",
        encoding="utf-8",
    )
    past = dest / "past"
    past.mkdir(exist_ok=True)
    lines = ["| id | status | type | mechanism | score |", "|---|---|---|---|---|"]
    for h in hyps:
        lines.append(
            f"| {h['id']} | {h['status']} | {h['type']} | {h['mechanism'][:80]} | {h.get('virtual_score') or ''} |"
        )
    (past / "INDEX.md").write_text("# INDEX\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    cem_lines = ["# Cemetery (mechanism classes)\n"]
    for c in cemetery:
        cem_lines.append(f"- **{c['mechanism_class']}**: {c['lesson']}")
    (past / "cemetery_mechanics.md").write_text("\n".join(cem_lines) + "\n", encoding="utf-8")
    tried = ["# Already tried\n", "Titles only. Full papers are not copied here.\n"]
    for row in store.recent_recall(project_id, limit=40):
        tried.append(f"- {row['kind']}: {row.get('title') or row.get('key')}")
    (past / "tried.md").write_text("\n".join(tried) + "\n", encoding="utf-8")
    run_lines = ["# Runs\n"]
    for r in runs:
        run_lines.append(f"- `{r['id']}` {r['phase']} {r['status']} metrics={r.get('metrics')}")
    (dest / "RUNS.md").write_text("\n".join(run_lines) + "\n", encoding="utf-8")
