from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

import yaml

from openrd.core.context import Context
from openrd.core.plugin import PluginManifest
from openrd.core.profile import Profile, load_profile, profiles_dir


def _plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent / "plugins"


def discover_manifests() -> list[PluginManifest]:
    manifests: list[PluginManifest] = []
    root = _plugin_root()
    if not root.exists():
        return manifests
    for yaml_path in sorted(root.glob("*/plugin.yaml")):
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        manifests.append(
            PluginManifest(
                id=raw["id"],
                provides=list(raw.get("provides") or []),
                requires=list(raw.get("requires") or []),
                title=raw.get("title") or raw["id"],
                description=raw.get("description") or "",
                tools=list(raw.get("tools") or []),
                when_to_use=raw.get("when_to_use") or "",
                bundle=raw.get("bundle") or "core",
                optional=bool(raw.get("optional", False)),
                module=raw.get("module") or f"openrd.plugins.{yaml_path.parent.name}",
                class_name=raw.get("class") or "Plugin",
            )
        )
    return manifests


def catalog() -> dict[str, PluginManifest]:
    return {m.id: m for m in discover_manifests()}


def _instantiate(manifest: PluginManifest) -> Any:
    module = importlib.import_module(manifest.module)
    cls = getattr(module, manifest.class_name)
    return cls()


def load_into(ctx: Context, profile: Profile | None = None, enabled: set[str] | None = None) -> None:
    manifests = catalog()
    if profile is None:
        default = profiles_dir() / "default.yaml"
        profile = load_profile(default)
    wanted = list(profile.bundles)
    if enabled is not None:
        wanted = [p for p in wanted if p in enabled] + [
            p for p in enabled if p not in wanted and p in manifests
        ]

    remaining = [pid for pid in wanted if pid in manifests]
    loaded: set[str] = set()
    safety = 0
    while remaining and safety < 200:
        safety += 1
        progressed = False
        for pid in list(remaining):
            man = manifests[pid]
            missing = [r for r in man.requires if r not in ctx._services and r not in loaded]
            # requires are service names, not plugin ids
            service_missing = [r for r in man.requires if not ctx.has(r)]
            if service_missing:
                # try later
                continue
            plugin = _instantiate(man)
            plugin.apply(ctx)
            ctx.register_plugin(pid, plugin)
            loaded.add(pid)
            remaining.remove(pid)
            progressed = True
        if not progressed:
            # load remaining anyway so optional deps don't deadlock
            pid = remaining.pop(0)
            man = manifests[pid]
            plugin = _instantiate(man)
            plugin.apply(ctx)
            ctx.register_plugin(pid, plugin)
            loaded.add(pid)

    ctx.extras["profile"] = profile
    ctx.extras["manifests"] = {k: v for k, v in manifests.items() if k in loaded}


def llm_plugin_catalog(ctx: Context) -> str:
    manifests: dict[str, PluginManifest] = ctx.extras.get("manifests") or catalog()
    lines = ["Available OpenRD plugins (use only these tools; do not invent APIs):"]
    for man in manifests.values():
        lines.append(man.to_llm_doc())
    return "\n".join(lines)


def is_plugin_class(obj: Any) -> bool:
    return inspect.isclass(obj) and hasattr(obj, "apply")
