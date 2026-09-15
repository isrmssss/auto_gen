from __future__ import annotations

from dataclasses import asdict, dataclass

import psutil


@dataclass
class HwSnapshot:
    cpu_count: int
    ram_total_mb: int
    ram_available_mb: int
    ram_used_frac: float
    swap_used_mb: int
    gpu: list[dict]
    recommended_exec_slots: int
    recommended_think_slots: int
    can_launch_exec: bool
    reason: str


def _gpus() -> list[dict]:
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=2,
        )
        gpus = []
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                gpus.append(
                    {
                        "name": parts[0],
                        "memory_total_mb": float(parts[1]),
                        "memory_free_mb": float(parts[2]),
                        "util": float(parts[3]),
                    }
                )
        return gpus
    except Exception:
        return []


def probe(memory_frac: float = 0.65, requested_exec: int = 1) -> HwSnapshot:
    vm = psutil.virtual_memory()
    ram_total = int(vm.total / 1024 / 1024)
    ram_avail = int(vm.available / 1024 / 1024)
    used_frac = 1.0 - (vm.available / vm.total if vm.total else 1.0)
    gpus = _gpus()
    # think slots are CPU/IO bound; cap by cores
    cores = psutil.cpu_count(logical=True) or 2
    think = max(1, min(16, cores))
    # exec: refuse if available RAM below 1.5GB or used > threshold
    can = ram_avail > 1500 and used_frac < memory_frac
    rec_exec = 0
    if can:
        rec_exec = max(1, min(requested_exec, ram_avail // 2500 or 1))
        if rec_exec < 1:
            rec_exec = 1
    if ram_avail < 1500:
        rec_exec = 0
        can = False
        reason = f"only {ram_avail}MB RAM free; refuse exec"
    elif used_frac >= memory_frac:
        rec_exec = 0
        can = False
        reason = f"RAM used {used_frac:.0%} exceeds {memory_frac:.0%} gate"
    else:
        reason = "ok"
        can = rec_exec >= 1
    if requested_exec > rec_exec and rec_exec >= 1:
        reason = f"clamped exec {requested_exec} → {rec_exec} by RAM"
    return HwSnapshot(
        cpu_count=cores,
        ram_total_mb=ram_total,
        ram_available_mb=ram_avail,
        ram_used_frac=round(used_frac, 4),
        swap_used_mb=int(psutil.swap_memory().used / 1024 / 1024),
        gpu=gpus,
        recommended_exec_slots=rec_exec,
        recommended_think_slots=think,
        can_launch_exec=can,
        reason=reason,
    )


def probe_dict(memory_frac: float = 0.65, requested_exec: int = 1) -> dict:
    return asdict(probe(memory_frac, requested_exec))
