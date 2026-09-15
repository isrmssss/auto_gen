# Eval harness

```bash
openrd eval --suite smoke
```

| Suite | What it measures | LLM needed |
| --- | --- | --- |
| `safety` | Malware/exploit treatments blocked; normal research allowed | no |
| `anti-loop` | Noise-floor refuses H132-style λ promote; refine quota blocks a dead line | no |
| `cipher` | General R&D verifier (Caesar). Not a millennium prize | no |
| `paper` | Quality bar rejects bare BERT, accepts compound adapter-style ideas | no |
| `tabular` | Quadratic feature beats mean baseline on synthetic RMSLE | no |
| `smoke` | All of the above | no |

Optional later (bring your own provider + time): Spaceship Titanic / MLE-bench lite, GAIA L1 subset. Those are **not** the hourly smoke — they belong in a night profile so cost stays visible in the UI ledger.

Metrics the UI already tracks for live runs: unique mechanism lines, repeats skipped, ₽, wall time, champion primary.
