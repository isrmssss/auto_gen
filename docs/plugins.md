# Adding a plugin

1. Create `src/openrd/plugins/<name>/plugin.yaml` and `__init__.py` with a `Plugin` class (`id`, `provides`, `requires`, `apply(ctx)`).
2. `ctx.provide("service_name", impl)` so others can `ctx.require("service_name")`.
3. Add the plugin id to `src/openrd/profiles/default.yaml` (or a domain profile).
4. Fill `when_to_use` — it is injected into the LLM tool catalog.

Do not import a new search vendor that bills per query. Prefer arXiv, OpenAlex, Semantic Scholar, Crossref, DBLP, OpenReview, Europe PMC, PubMed, Zenodo, HAL, DOAJ, GitHub, or a self-hosted SearXNG sidecar. Download full text only from the allowlist in `search_common.py`. Treat fetched pages as untrusted data.
