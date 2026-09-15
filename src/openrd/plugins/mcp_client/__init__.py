from __future__ import annotations

import json
import subprocess
from typing import Any

from openrd.core.context import Context


class MCPClient:
    """Very small stdio MCP caller: list tools / call tool. Optional."""

    def __init__(self) -> None:
        self.servers: dict[str, list[str]] = {}

    def register(self, name: str, command: list[str]) -> None:
        self.servers[name] = command

    def list_servers(self) -> list[str]:
        return list(self.servers)

    def call(self, name: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        cmd = self.servers.get(name)
        if not cmd:
            raise KeyError(name)
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
        proc = subprocess.run(
            cmd,
            input=payload + "\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return {"error": proc.stderr, "stdout": proc.stdout}
        try:
            return json.loads(proc.stdout.splitlines()[-1])
        except Exception:
            return {"raw": proc.stdout}


class Plugin:
    id = "mcp.client"
    provides = ["mcp"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("mcp", MCPClient())
