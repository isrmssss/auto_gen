from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from openrd.core.context import Context

BANNED_NAME_RE = re.compile(
    r"(exploit|malware|ransomware|keylogger|backdoor|rootkit|payload\.bin|meterpreter)",
    re.I,
)

BANNED_HYP_RE = re.compile(
    r"(write (a |an )?(virus|worm|ransomware)|exploit CVE|sql injection payload|"
    r"bypass (the )?censor by attacking|exfiltrate secrets|steal (api|ssh) keys)",
    re.I,
)

DANGEROUS_CALLS = {
    ("os", "system"),
    ("os", "popen"),
    ("subprocess", "call"),
    ("subprocess", "Popen"),
    ("subprocess", "run"),
    ("ctypes", "CDLL"),
    ("socket", "socket"),
}


@dataclass
class SafetyVerdict:
    ok: bool
    reasons: list[str]


class SafetyService:
    def check_hypothesis(self, text: str) -> SafetyVerdict:
        reasons = []
        if BANNED_HYP_RE.search(text or ""):
            reasons.append("hypothesis describes a harmful executable treatment")
        if BANNED_NAME_RE.search(text or ""):
            reasons.append("hypothesis name/text matches malware/exploit vocabulary")
        # research discussion is allowed if it clearly says "do not implement"
        if "do not implement" in (text or "").lower() and reasons:
            reasons = [r for r in reasons if "vocabulary" not in r]
        return SafetyVerdict(ok=not reasons, reasons=reasons)

    def check_code(self, code: str, filename: str = "treatment.py") -> SafetyVerdict:
        reasons = []
        if BANNED_NAME_RE.search(filename) or BANNED_NAME_RE.search(code[:500]):
            reasons.append("filename or header looks like malware")
        if re.search(r"(\/\.ssh|id_rsa|\.aws\/credentials|\/etc\/shadow)", code):
            reasons.append("code reads host secrets")
        if re.search(r"while\s+True\s*:\s*(os\.fork|threading\.Thread)", code):
            reasons.append("fork-bomb pattern")
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return SafetyVerdict(ok=False, reasons=[f"syntax error: {e}"])
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                pair = (node.value.id, node.attr)
                if pair in {("os", "fork"), ("os", "kill"), ("os", "chmod")}:
                    reasons.append(f"dangerous attribute {pair}")
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    if (func.value.id, func.attr) in DANGEROUS_CALLS:
                        # allow subprocess only if args are clearly local python scripts
                        reasons.append(
                            f"disallowed call {func.value.id}.{func.attr} — use the sandbox runner, not raw process spawn"
                        )
                if isinstance(func, ast.Name) and func.id in {"eval", "exec", "compile"}:
                    reasons.append(f"disallowed builtin {func.id}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {"ctypes", "pty", "telnetlib"}:
                        reasons.append(f"disallowed import {alias.name}")
        # network in experiment code is denied unless commented allow
        if re.search(r"(requests\.|httpx\.|urllib\.request)", code) and "OPENRD_ALLOW_NET" not in code:
            reasons.append("network client in experiment code (default deny)")
        return SafetyVerdict(ok=not reasons, reasons=reasons)


class Plugin:
    id = "safety.policy"
    provides = ["safety"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("safety", SafetyService())
