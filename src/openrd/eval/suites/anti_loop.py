"""Noisy landscape: tiny λ tweaks must not promote (Ozon H132 autopsy)."""

from __future__ import annotations

from typing import Any

from openrd.plugins.rnd_search_policy import SearchPolicy
from openrd.plugins.tracker_runs import Tracker
from openrd.db.store import Store
from openrd.paths import home_dir


def run(provider_id: str | None = None) -> dict[str, Any]:
    tracker = Tracker()
    # champion 1.665237, treatment 1.665223 — noise
    gate = tracker.noise_gate(
        values=[1.66524, 1.66521, 1.66526],
        delta=-0.000014,
        promote_min=0.0005,
    )
    # Search policy: three refines of one line should block the fourth
    db = Store(home_dir() / "eval-anti-loop.sqlite")
    pid = "anti"
    db.execute(
        """INSERT OR REPLACE INTO projects(
            id,name,goal,description,kpi_json,profile,think_slots,exec_slots,status,
            workspace_path,created_at,updated_at,last_event_seq)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            pid,
            "anti",
            "metric",
            "",
            "{}",
            "default",
            1,
            1,
            "idle",
            str(home_dir() / "ws"),
            "t",
            "t",
            0,
        ),
    )
    for i in range(3):
        db.add_hypothesis(
            {
                "project_id": pid,
                "line_id": "recency-lambda",
                "type": "refine",
                "mechanism": "recency λ",
                "fingerprint": f"r{i}",
                "text": f"tune lambda {i}",
                "status": "tested",
            }
        )
    pol = SearchPolicy()
    pol.store = db
    pol.bind(pid)
    allowed = pol.allowed_types()
    filtered = pol.filter_portfolio(
        [
            {"type": "refine", "line": "recency-lambda", "mechanism": "recency λ=0.02"},
            {"type": "explore", "line": "midband-transformer", "mechanism": "seq model on mid band"},
        ]
    )
    blocked = "recency-lambda" in allowed["blocked_refine_lines"]
    kept_refine = any(h["type"] == "refine" and "recency" in h["line"] for h in filtered)
    ok = (not gate["promote"]) and gate["tie"] and blocked and not kept_refine
    return {
        "name": "anti_loop",
        "ok": ok,
        "score": 1.0 if ok else 0.0,
        "detail": {"gate": gate, "allowed": {k: allowed[k] for k in ("prefer", "blocked_refine_lines")}},
    }
