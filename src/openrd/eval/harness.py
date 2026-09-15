from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openrd.eval.suites import anti_loop, cipher, paper_to_hyp, safety_gate, tabular


@dataclass
class CaseResult:
    name: str
    ok: bool
    score: float
    cost_rub: float | None
    seconds: float
    detail: dict


def run_suite(suite: str, provider_id: str | None = None) -> int:
    t0 = time.time()
    runners = {
        "smoke": [safety_gate.run, anti_loop.run, cipher.run, paper_to_hyp.run, tabular.run],
        "anti-loop": [anti_loop.run],
        "cipher": [cipher.run],
        "paper": [paper_to_hyp.run],
        "tabular": [tabular.run],
        "safety": [safety_gate.run],
    }
    fns = runners.get(suite)
    if not fns:
        print(f"unknown suite {suite}; choose {list(runners)}")
        return 2
    results: list[CaseResult] = []
    for fn in fns:
        started = time.time()
        raw: dict[str, Any] = fn(provider_id=provider_id)
        results.append(
            CaseResult(
                name=raw["name"],
                ok=bool(raw["ok"]),
                score=float(raw.get("score") or 0),
                cost_rub=raw.get("cost_rub"),
                seconds=time.time() - started,
                detail=raw.get("detail") or {},
            )
        )
    payload = {
        "suite": suite,
        "seconds": time.time() - t0,
        "passed": sum(1 for r in results if r.ok),
        "total": len(results),
        "results": [asdict(r) for r in results],
    }
    out = Path("data") / "eval"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{suite}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if all(r.ok for r in results) else 1
