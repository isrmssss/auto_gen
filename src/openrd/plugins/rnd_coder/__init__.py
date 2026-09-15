from __future__ import annotations

from typing import Any

from openrd.core.context import Context
from openrd.settings import settings

SYS = """You write a single Python script for an isolated sandbox.
Constraints:
- Print a line METRICS:{"primary": <float>, ...} on success.
- No network, no host secrets, no subprocess, no os.system.
- Read only files under the current directory.
- Prefer numpy/stdlib. If data is missing, synthesize a tiny deterministic evaluation that still tests the MECHANISM (not a stub that always returns 0).
- Sample mode: env OPENRD_SAMPLE=1 means use a small subset / fewer steps.
Return ONLY the python source, no markdown fences.
"""


class Coder:
    def __init__(self) -> None:
        self.ctx: Context | None = None

    def bind(self, ctx: Context) -> None:
        self.ctx = ctx

    async def write(self, hyp: dict[str, Any], sample: bool = True) -> str:
        assert self.ctx
        llm = self.ctx.require("llm")
        res = await llm.complete(
            "coder",
            [
                {
                    "role": "user",
                    "content": (
                        f"SAMPLE={sample} fraction={settings.sample_fraction}\n"
                        f"MECHANISM={hyp.get('mechanism')}\n"
                        f"SKETCH={hyp.get('sketch')}\n"
                        f"IDEA={hyp.get('text')}\n"
                    ),
                }
            ],
            system=SYS,
            temperature=0.2,
        )
        code = res.text.strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[-1]
            if code.endswith("```"):
                code = code[: code.rfind("```")]
        return code

    async def repair(self, code: str, stderr: str) -> str:
        assert self.ctx
        llm = self.ctx.require("llm")
        res = await llm.complete(
            "coder",
            [
                {
                    "role": "user",
                    "content": f"Fix this sandbox script.\nSTDERR:\n{stderr[-4000:]}\n\nCODE:\n{code}",
                }
            ],
            system=SYS,
            temperature=0.1,
        )
        out = res.text.strip()
        if out.startswith("```"):
            out = out.split("\n", 1)[-1]
            if out.endswith("```"):
                out = out[: out.rfind("```")]
        return out


class Plugin:
    id = "rnd.coder"
    provides = ["coder"]
    requires = ["llm", "sandbox", "safety"]

    def apply(self, ctx: Context) -> None:
        svc = Coder()
        svc.bind(ctx)
        ctx.provide("coder", svc)
