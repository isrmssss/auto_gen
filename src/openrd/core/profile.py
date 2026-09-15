from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Profile:
    name: str
    bundles: list[str] = field(default_factory=list)
    patch: dict[str, Any] = field(default_factory=dict)


def load_profile(path: Path) -> Profile:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Profile(
        name=data.get("name") or path.stem,
        bundles=list(data.get("bundles") or []),
        patch=dict(data.get("patch") or {}),
    )


def profiles_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "profiles"
