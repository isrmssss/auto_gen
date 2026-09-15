# OpenRD contributor notes

This repository is the OpenRD runtime, not a Cursor-only hypothesis markdown kit.

- Product code: `src/openrd/`
- UI: `ui/`
- Plugin contract: `plugin.yaml` + `Plugin.apply(ctx)` providing services
- Do not treat a project's `knowledge/` export as source of truth; it is a projection of the journal
- Safety: never weaken `safety.policy` to allow host escape, secret reads, or malware treatments
- Paid search APIs are out of scope; add free/self-hosted plugins instead

Run tests: `pytest`. Run smoke eval: `openrd eval --suite smoke`.
