"""Paper-to-hypothesis: a compound idea must beat a BERT-only stub."""

from __future__ import annotations

from typing import Any

from openrd.plugins.rnd_quality_bar import QualityBar


def run(provider_id: str | None = None) -> dict[str, Any]:
    bar = QualityBar()
    naive = bar.cheap_check("bert", "just bert")
    compound = bar.cheap_check(
        "BERT + adapter (ADA) + focal loss on long-tail classes",
        "Baseline is a frozen BERT CLS head. Trigger: long-tail labels dominate error. "
        "Action: insert a bottleneck adapter after each transformer block, train with focal loss, "
        "keep tokenizer and max-len frozen. Expected: macro-F1 up without full fine-tune cost.",
    )
    ok = (not naive["ok"]) and compound["ok"]
    return {
        "name": "paper_to_hyp",
        "ok": ok,
        "score": 1.0 if ok else 0.0,
        "detail": {"naive": naive, "compound": compound},
    }
