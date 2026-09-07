"""Readers for the kernel memory stack: meminfo, zswap, MGLRU, DAMON, PSI, cgroups."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

PAGE_SIZE = 4096


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _read_int(path: Path) -> int | None:
    value = _read(path)
    if value is None:
        return None
    for base in (10, 16):
        try:
            return int(value, base)
        except ValueError:
            continue
    return None


def meminfo() -> dict[str, int]:
    """Parse /proc/meminfo into a kB map (missing keys absent)."""
    text = _read(paths.proc() / "meminfo")
    out: dict[str, int] = {}
    if not text:
        return out
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        digits = re.match(r"\s*(\d+)", rest)
        if digits:
            out[key] = int(digits.group(1))
    return out


def memtotal_kb() -> int | None:
    return meminfo().get("MemTotal")


def detect_mode(total_kb: int) -> str:
    """The firstboot calibration rule: <6 GiB saver, 6-16 balanced, >16 performance."""
    total_mb = total_kb // 1024
    if total_mb < 6144:
        return "saver"
    if total_mb <= 16384:
        return "balanced"
    return "performance"


@dataclass
class ZswapParams:
    enabled: bool | None = None
    compressor: str | None = None
    max_pool_percent: int | None = None
    shrinker: bool | None = None
    zpool: str | None = None
    zpool_param_exists: bool = False


@dataclass
class ZswapStats:
    pool_total_size: int | None = None
    stored_pages: int | None = None
    same_filled_pages: int | None = None
    compressed_ratio: float | None = None
    pool_cap_bytes: int | None = None

    @property
    def approximates(self) -> bool:
        return self.pool_total_size not in (None, 0) and self.stored_pages


def zswap_params() -> ZswapParams:
    base = paths.sysfs() / "module/zswap/parameters"
    enabled = _read(base / "enabled")
    zpool = _read(base / "zpool")
    return ZswapParams(
        enabled=None if enabled is None else enabled == "Y",
        compressor=_read(base / "compressor"),
        max_pool_percent=_read_int(base / "max_pool_percent"),
        shrinker=None if (s := _read(base / "shrinker_enabled")) is None else s == "Y",
        zpool=zpool,
        zpool_param_exists=zpool is not None,
    )


def zswap_stats(memtotal_kb: int | None = None) -> ZswapStats:
    """Live pool numbers from debugfs (root-only on most systems)."""
    base = paths.sysfs() / "kernel/debug/zswap"
    pool_total = _read_int(base / "pool_total_size")
    stored = _read_int(base / "stored_pages")
    same = _read_int(base / "same_filled_pages")
    ratio = None
    if pool_total and stored:
        ratio = stored * PAGE_SIZE / pool_total
    cap = None
    pct = zswap_params().max_pool_percent
    if pct is not None and memtotal_kb is not None:
        cap = memtotal_kb * 1024 * pct // 100
    return ZswapStats(
        pool_total_size=pool_total,
        stored_pages=stored,
        same_filled_pages=same,
        compressed_ratio=ratio,
        pool_cap_bytes=cap,
    )


@dataclass
class Mglru:
    enabled: int | None = None
    min_ttl_ms: int | None = None


def mglru() -> Mglru:
    base = paths.sysfs() / "kernel/mm/lru_gen"
    return Mglru(enabled=_read_int(base / "enabled"), min_ttl_ms=_read_int(base / "min_ttl_ms"))


def damon_state() -> str | None:
    return _read(paths.sysfs() / "kernel/mm/damon/admin/kdamonds/0/state")


@dataclass
class Psi:
    some_avg10: float | None = None
    some_avg60: float | None = None
    full_avg10: float | None = None
    full_avg60: float | None = None


def psi_memory() -> Psi | None:
    text = _read(paths.proc() / "pressure/memory")
    if text is None:
        return None
    values: dict[str, dict[str, float]] = {}
    for line in text.splitlines():
        kind, _, rest = line.partition(" ")
        fields: dict[str, float] = {}
        for match in re.finditer(r"(avg10|avg60|avg300|total)=([0-9.]+)", rest):
            fields[match.group(1)] = float(match.group(2))
        values[kind] = fields
    some, full = values.get("some", {}), values.get("full", {})
    return Psi(
        some_avg10=some.get("avg10"),
        some_avg60=some.get("avg60"),
        full_avg10=full.get("avg10"),
        full_avg60=full.get("avg60"),
    )


def user_slice_memory_high() -> int | None:
    value = _read(paths.sysfs() / "fs/cgroup/user.slice/memory.high")
    if value is None or value == "max":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def top_cgroups(limit: int = 6) -> list[tuple[str, int]]:
    """Largest memory consumers among cgroups two levels below the root."""
    base = paths.sysfs() / "fs/cgroup"
    entries: list[tuple[str, int]] = []
    try:
        level1 = [child for child in base.iterdir() if child.is_dir()]
    except OSError:
        return []
    for child in level1:
        current = _read_int(child / "memory.current")
        if current:
            entries.append((child.name, current))
        try:
            level2 = [gchild for gchild in child.iterdir() if gchild.is_dir()]
        except OSError:
            continue
        for gchild in level2:
            current = _read_int(gchild / "memory.current")
            if current:
                entries.append((f"{child.name}/{gchild.name}", current))
    entries.sort(key=lambda item: item[1], reverse=True)
    return entries[:limit]


def thp_mode() -> str | None:
    value = _read(paths.sysfs() / "kernel/mm/transparent_hugepage/enabled")
    match = re.search(r"\[(\w+)\]", value or "")
    return match.group(1) if match else value


@dataclass
class Stack:
    """Everything `kutu status` shows, gathered once."""

    memtotal_kb: int | None = None
    memavailable_kb: int | None = None
    swaptotal_kb: int | None = None
    swapfree_kb: int | None = None
    zswap: ZswapParams = field(default_factory=ZswapParams)
    zswap_live: ZswapStats = field(default_factory=ZswapStats)
    lru: Mglru = field(default_factory=Mglru)
    damon: str | None = None
    psi: Psi | None = None
    user_high: int | None = None
    thp: str | None = None
    oomd_active: bool | None = None
    mode: str | None = None
    recommended_mode: str | None = None


def gather(include_services: bool = True) -> Stack:
    from . import mode as mode_mod
    from . import system

    info = meminfo()
    total = info.get("MemTotal")
    live = zswap_stats(total)
    stack = Stack(
        memtotal_kb=total,
        memavailable_kb=info.get("MemAvailable"),
        swaptotal_kb=info.get("SwapTotal"),
        swapfree_kb=info.get("SwapFree"),
        zswap=zswap_params(),
        zswap_live=live,
        lru=mglru(),
        damon=damon_state(),
        psi=psi_memory(),
        user_high=user_slice_memory_high(),
        thp=thp_mode(),
        oomd_active=system.service_active("systemd-oomd") if include_services else None,
        mode=mode_mod.current_mode(),
        recommended_mode=detect_mode(total) if total else None,
    )
    return stack
