# OpenRD

Local-first **R&D agent**: you describe a hard goal, the system researches (free search), debates compound hypotheses, runs them in a sandbox, remembers what failed, and keeps going until you stop it — or a verifier says the goal is met.

This is not a markdown protocol for Cursor. It is a runnable product: plugin kernel, FastAPI, React UI, experiment tracker, cost ledger, and a hardware-gated executor.

You pay **only** the LLM API (Polza, OpenAI, Ollama, …). Search, parsing, memory, and orchestration are open-source and self-hosted.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd ui && npm install && npm run build && cd ..
openrd serve --host 127.0.0.1 --port 8080
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080).

1. **Providers** — base URL `https://polza.ai/api/v1`, API key, role models (orchestrator / researcher / critic / coder).
2. **New project** — isolated workspace, goal, optional ideas/PDFs, agent count `1 | 5 | 10 | 15`.
3. **Start** — watch the tree, metrics, ₽ ledger. Steer, drop papers, pause, rollback to a node, resume.

Optional web search sidecar (AGPL, not linked into our MIT code):

```bash
docker compose -f deploy/docker-compose.yml up searxng
export OPENRD_SEARXNG_URL=http://127.0.0.1:8888
```

Full stack:

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## What it does that the old auto_gen protocol did not

| Old | OpenRD |
| --- | --- |
| Instructions in `AGENTS.md` | Enforced runtime (cemetery, noise gate, quotas, URL/query locks) |
| Ideas from chat dumps | Research plugins → debate → virtual eval → then code |
| Host-side scripts | Docker/rlimit sandbox, network deny, safety critic |
| No UI | Tree, ClearML-style metrics, cost, human steer |
| Context stuffed with INDEX | Core blocks + compiler brief + archive search |

## Architecture

Micro-kernel (`Context`: services, events, reversible plugins) + YAML **profiles**. Adding a source is a plugin folder + one bundle line. The LLM sees the generated catalog.

Default plugins: LLM (OpenAI-compat), local embeddings, journal/core/archive/graph/compiler memory, SearXNG/arXiv/S2/OpenAlex/GitHub, Docling ingest, safety, sandbox, HW scheduler, tracker, MCP client, human steer, scientist/debate/virtual-eval/quality-bar/coder/analyst/orchestrator, ML / product / general-research domains.

## Eval (1–2 hour smoke, no paid search)

```bash
openrd eval --suite smoke
```

Suites: `smoke` (safety, anti-loop/noise promote, cipher verifier, paper-to-hyp quality bar, tabular RMSLE), plus `anti-loop`, `cipher`, `paper`, `tabular`, `safety`.

Night-scale MLE-bench / GAIA are out of the hourly suite on purpose.

## Layout

```
src/openrd/core/      plugin kernel
src/openrd/plugins/   everything else is a plugin
src/openrd/server/    FastAPI + WebSocket
src/openrd/engine/    orchestrator loop, bus, HW probe
src/openrd/eval/      harness
ui/                   React control UI
deploy/               Docker Compose + SearXNG sidecar
```

License: MIT. SearXNG remains a separate AGPL container.

## Name

The git repo may still be `auto_gen`. The product and Python package are **openrd** (avoids colliding with Microsoft AutoGen).
