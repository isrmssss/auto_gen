"""Synthetic tabular: a linear model vs a known better quadratic feature."""

from __future__ import annotations

from typing import Any

import numpy as np


def rmsle(y, p) -> float:
    y = np.clip(y, 0, None)
    p = np.clip(p, 0, None)
    return float(np.sqrt(np.mean((np.log1p(y) - np.log1p(p)) ** 2)))


def run(provider_id: str | None = None) -> dict[str, Any]:
    rng = np.random.default_rng(0)
    x = rng.normal(size=400)
    y = np.clip(np.exp(0.4 * x + 0.15 * x**2) - 1, 0, None)
    # naive: predict mean
    naive = rmsle(y, np.full_like(y, y.mean()))
    # compound: quadratic features
    X = np.column_stack([np.ones_like(x), x, x**2])
    beta, *_ = np.linalg.lstsq(X, np.log1p(y), rcond=None)
    pred = np.expm1(X @ beta)
    smart = rmsle(y, pred)
    ok = smart + 1e-6 < naive
    return {
        "name": "tabular_smoke",
        "ok": ok,
        "score": float(naive - smart),
        "detail": {"naive_rmsle": naive, "quad_rmsle": smart},
    }
