"""Tiny Caesar decipherment with a verifier — general R&D, not ML."""

from __future__ import annotations

from typing import Any

CIPHER = "wkhtxlfneurzqiramxpsvryhuwkhodcbgrj"  # thequickbrownfoxjumpsoverthelazydog shift 3
PLAIN = "thequickbrownfoxjumpsoverthelazydog"


def score_shift(shift: int) -> float:
    out = []
    for ch in CIPHER:
        out.append(chr((ord(ch) - 97 - shift) % 26 + 97))
    guess = "".join(out)
    return float(sum(a == b for a, b in zip(guess, PLAIN))) / len(PLAIN)


def brute() -> tuple[int, float]:
    best_s, best = 0, -1.0
    for s in range(26):
        sc = score_shift(s)
        if sc > best:
            best, best_s = sc, s
    return best_s, best


def run(provider_id: str | None = None) -> dict[str, Any]:
    shift, sc = brute()
    ok = sc == 1.0 and shift == 3
    return {
        "name": "cipher",
        "ok": ok,
        "score": sc,
        "detail": {"shift": shift, "note": "verifier exists; millenium problems are out of scope for 2h"},
    }
