"""Per-application ceiling profiles (/etc/kutu/apps.d) and the scoped launcher.

Mirrors ``kutu-run`` from kutu-base: unique scope names, no environment
expansion, systemd-run as the execution vehicle.
"""

from __future__ import annotations

import dataclasses
import os
import random
import re

from . import paths


@dataclasses.dataclass
class AppProfile:
    name: str
    memory_high_pct: int | None = None
    memory_swap_max: str | None = None
    cpu_weight: int | None = None
    memory_merge: bool = False
    source: str = ""


def _parse(path) -> AppProfile:
    profile = AppProfile(name=path.stem, source=str(path))
    try:
        text = path.read_text()
    except OSError:
        return profile
    for line in text.splitlines():
        match = re.match(r"\s*([A-Z_]+)\s*=\s*(.*?)\s*$", line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if key == "KUTU_MEMORY_HIGH_PCT" and value.isdigit():
            profile.memory_high_pct = int(value)
        elif key == "KUTU_MEMORY_SWAP_MAX":
            profile.memory_swap_max = value
        elif key == "KUTU_CPU_WEIGHT" and value.isdigit():
            profile.cpu_weight = int(value)
        elif key == "KUTU_MEMORY_MERGE":
            profile.memory_merge = value == "1"
    return profile


def list_apps() -> list[AppProfile]:
    apps = paths.apps_dir()
    if not apps.is_dir():
        return []
    return [_parse(conf) for conf in sorted(apps.glob("*.conf"))]


def get_app(name: str) -> AppProfile | None:
    conf = paths.apps_dir() / f"{name}.conf"
    return _parse(conf) if conf.is_file() else None


def effective_memory_high(profile: AppProfile, memtotal_kb: int | None) -> int | None:
    if profile.memory_high_pct is None or not memtotal_kb:
        return None
    return memtotal_kb * 1024 * profile.memory_high_pct // 100


def build_scope_command(profile: AppProfile, argv: list[str], memtotal_kb: int | None) -> list[str]:
    """The exact systemd-run invocation kutu-run would build."""
    cmd = [*paths.systemd_run_cmd(), "--user", "--scope", "--expand-environment=no"]
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", profile.name).lstrip(".")
    unit = f"app-{safe}-{os.getpid()}-{random.randint(0, 65535)}"
    cmd.append(f"--unit={unit}")
    if (high := effective_memory_high(profile, memtotal_kb)) is not None:
        cmd.append(f"-p MemoryHigh={high}")
    if profile.memory_swap_max is not None:
        cmd.append(f"-p MemorySwapMax={profile.memory_swap_max}")
    if profile.cpu_weight is not None:
        cmd.append(f"-p CPUWeight={profile.cpu_weight}")
    if profile.memory_merge:
        cmd.append("-p MemoryMerge=yes")
    cmd.append("--")
    cmd.extend(argv)
    return cmd
