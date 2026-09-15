from __future__ import annotations

import os
from pathlib import Path


def home_dir() -> Path:
    raw = os.environ.get("OPENRD_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.cwd() / "data").resolve()


def db_path() -> Path:
    p = home_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p / "openrd.sqlite"


def secrets_path() -> Path:
    p = home_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p / "secrets.json"


def workspaces_root() -> Path:
    raw = os.environ.get("OPENRD_WORKSPACES")
    if raw:
        root = Path(raw).expanduser().resolve()
    else:
        root = (Path.cwd() / "workspaces").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_workspace(project_id: str) -> Path:
    path = workspaces_root() / project_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "work").mkdir(exist_ok=True)
    (path / "artifacts").mkdir(exist_ok=True)
    (path / "runs").mkdir(exist_ok=True)
    (path / "knowledge").mkdir(exist_ok=True)
    return path
