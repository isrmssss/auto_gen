from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openrd.core.context import Context


@dataclass
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    backend: str = "local"
    log_path: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


class Sandbox:
    def __init__(self) -> None:
        self.work_dir: Path | None = None
        self.memory_mb: int = 2048
        self.timeout_s: int = 180

    def bind(self, work_dir: Path, memory_mb: int = 2048, timeout_s: int = 180) -> None:
        self.work_dir = work_dir
        self.memory_mb = memory_mb
        self.timeout_s = timeout_s
        work_dir.mkdir(parents=True, exist_ok=True)

    def _docker_available(self) -> bool:
        try:
            subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=False)
            return True
        except Exception:
            return False

    def run_python(
        self,
        code: str,
        filename: str = "treatment.py",
        extra_files: dict[str, str] | None = None,
        timeout_s: int | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        assert self.work_dir
        timeout = timeout_s or self.timeout_s
        target = self.work_dir / filename
        target.write_text(code, encoding="utf-8")
        for name, body in (extra_files or {}).items():
            p = self.work_dir / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        if self._docker_available():
            return self._run_docker(filename, timeout, env)
        return self._run_local(filename, timeout, env)

    def _run_local(self, filename: str, timeout: int, env: dict[str, str] | None) -> SandboxResult:
        assert self.work_dir
        run_env = os.environ.copy()
        run_env["PYTHONHASHSEED"] = "0"
        run_env["OPENRD_SANDBOX"] = "1"
        if env:
            run_env.update(env)
        # drop secrets
        for k in list(run_env):
            if "KEY" in k.upper() or "TOKEN" in k.upper() or "SECRET" in k.upper():
                if k not in (env or {}):
                    run_env.pop(k, None)

        def _preexec() -> None:
            try:
                import resource

                mem = self.memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
                resource.setrlimit(resource.RLIMIT_CPU, (timeout + 2, timeout + 2))
                resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            except Exception:
                pass

        t0 = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, filename],
                cwd=str(self.work_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env,
                preexec_fn=_preexec if os.name == "posix" else None,
            )
            duration = time.time() - t0
            log_path = self._write_log(filename, proc.stdout, proc.stderr, duration)
            return SandboxResult(
                returncode=proc.returncode,
                stdout=proc.stdout[-20_000:],
                stderr=proc.stderr[-20_000:],
                duration_s=duration,
                backend="local",
                log_path=log_path,
                metrics=_parse_metrics(proc.stdout),
            )
        except subprocess.TimeoutExpired as e:
            duration = time.time() - t0
            out = (e.stdout or "") if isinstance(e.stdout, str) else ""
            err = (e.stderr or "") if isinstance(e.stderr, str) else "timeout"
            log_path = self._write_log(filename, out, err, duration)
            return SandboxResult(
                returncode=124,
                stdout=out[-20_000:],
                stderr="timed out",
                duration_s=duration,
                timed_out=True,
                backend="local",
                log_path=log_path,
            )

    def _run_docker(self, filename: str, timeout: int, env: dict[str, str] | None) -> SandboxResult:
        assert self.work_dir
        env_args: list[str] = ["-e", "PYTHONHASHSEED=0", "-e", "OPENRD_SANDBOX=1"]
        for k, v in (env or {}).items():
            env_args.extend(["-e", f"{k}={v}"])
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            f"{self.memory_mb}m",
            "--cpus",
            "1.5",
            "--pids-limit",
            "64",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "-v",
            f"{self.work_dir}:/work:rw",
            "-w",
            "/work",
            *env_args,
            "python:3.12-slim",
            "python",
            filename,
        ]
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
            duration = time.time() - t0
            log_path = self._write_log(filename, proc.stdout, proc.stderr, duration)
            return SandboxResult(
                returncode=proc.returncode,
                stdout=proc.stdout[-20_000:],
                stderr=proc.stderr[-20_000:],
                duration_s=duration,
                backend="docker",
                log_path=log_path,
                metrics=_parse_metrics(proc.stdout),
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - t0
            log_path = self._write_log(filename, "", "timed out", duration)
            return SandboxResult(
                returncode=124,
                stdout="",
                stderr="timed out",
                duration_s=duration,
                timed_out=True,
                backend="docker",
                log_path=log_path,
            )
        except FileNotFoundError:
            return self._run_local(filename, timeout, env)

    def _write_log(self, filename: str, stdout: str, stderr: str, duration: float) -> str:
        assert self.work_dir
        log_dir = self.work_dir.parent / "runs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{int(time.time())}_{filename}.log"
        path.write_text(
            f"file={filename} duration={duration:.2f}s\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n",
            encoding="utf-8",
        )
        return str(path)


def _parse_metrics(stdout: str) -> dict[str, float]:
    import json
    import re

    metrics: dict[str, float] = {}
    for line in stdout.splitlines():
        if line.startswith("METRICS:"):
            try:
                data = json.loads(line[len("METRICS:") :].strip())
                for k, v in data.items():
                    metrics[str(k)] = float(v)
            except Exception:
                pass
        m = re.match(r"metric[.\s]+([a-zA-Z0-9_]+)\s*[:=]\s*([-+0-9.eE]+)", line)
        if m:
            metrics[m.group(1)] = float(m.group(2))
    return metrics


class Plugin:
    id = "sandbox.docker"
    provides = ["sandbox"]
    requires = ["safety"]

    def apply(self, ctx: Context) -> None:
        ctx.provide("sandbox", Sandbox())
