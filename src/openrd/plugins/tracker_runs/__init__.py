from __future__ import annotations

import math
from typing import Any

import numpy as np

from openrd.core.context import Context
from openrd.db.store import get_store


class Tracker:
    def __init__(self) -> None:
        self.store = get_store()
        self.project_id: str | None = None

    def bind(self, project_id: str) -> None:
        self.project_id = project_id

    def start_run(self, **kwargs: Any) -> dict[str, Any]:
        assert self.project_id
        kwargs.setdefault("project_id", self.project_id)
        return self.store.add_run(kwargs)

    def log_metrics(self, run_id: str, metrics: dict[str, float], step: int = 0) -> None:
        for name, value in metrics.items():
            self.store.add_metric_point(run_id, name, float(value), step=step)
        run = self.store.get_run(run_id)
        base = ((run or {}).get("metrics") or {})
        merged = {**base, **metrics}
        self.store.update_run(run_id, metrics=merged)

    def finish(self, run_id: str, status: str, metrics: dict[str, float] | None = None) -> None:
        if metrics:
            self.log_metrics(run_id, metrics)
        from datetime import datetime, timezone

        self.store.update_run(
            run_id, status=status, finished_at=datetime.now(timezone.utc).isoformat()
        )

    def compare(self, treatment: dict[str, float], champion: dict[str, float], higher_is_better: dict[str, bool] | None = None) -> dict[str, Any]:
        hib = higher_is_better or {}
        deltas = {}
        for k, v in treatment.items():
            if k in champion:
                deltas[k] = v - float(champion[k])
        return {"deltas": deltas, "keys": list(deltas)}

    def noise_gate(
        self,
        values: list[float],
        delta: float,
        promote_min: float = 0.0005,
        alpha: float = 0.05,
    ) -> dict[str, Any]:
        arr = np.array(values, dtype=float)
        if arr.size < 2:
            sigma = float(abs(delta) * 2 + 1e-6)
        else:
            sigma = float(arr.std(ddof=1))
        # crude bootstrap CI on mean of deltas ~ N(delta, sigma)
        samples = np.random.default_rng(0).normal(delta, max(sigma, 1e-12), size=2000)
        lo, hi = np.quantile(samples, [alpha / 2, 1 - alpha / 2])
        p_worse = float((samples > 0).mean()) if delta < 0 else float((samples < 0).mean())
        promote = abs(delta) > promote_min and not (lo <= 0 <= hi)
        return {
            "sigma": sigma,
            "ci": [float(lo), float(hi)],
            "p_worse": p_worse,
            "promote": bool(promote),
            "tie": abs(delta) <= promote_min or (lo <= 0 <= hi),
        }

    def project_metrics(self) -> list[dict[str, Any]]:
        assert self.project_id
        return self.store.metrics_for_project(self.project_id)


class Plugin:
    id = "tracker.runs"
    provides = ["tracker"]
    requires = ["journal"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("tracker", Tracker())
