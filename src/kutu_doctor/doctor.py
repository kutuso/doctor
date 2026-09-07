"""Health checks: the kutu-check-kernel contract plus service and config checks."""

from __future__ import annotations

from dataclasses import dataclass

from . import memory, paths, system


@dataclass
class Check:
    name: str
    ok: bool | None
    detail: str
    hint: str | None = None


def _file(p) -> bool:
    return p.is_file()


def kernel_checks() -> list[Check]:
    sys = paths.sysfs()
    proc = paths.proc()
    zp = memory.zswap_params()
    lru = memory.mglru()
    thp = memory.thp_mode()

    zpool_detail = (
        f"zsmalloc default (param absent on kernels >= 6.10) or explicit; got {zp.zpool or 'none'}"
    )
    lru_detail = (
        f"enabled={format(lru.enabled, '#06x')}" if lru.enabled is not None else "enabled=none"
    )

    return [
        Check(
            "zswap",
            zp.enabled is not None and zp.enabled,
            f"enabled={'Y' if zp.enabled else 'N' if zp.enabled is not None else '?'}",
            "the memory stack needs zswap; check the kernel command line",
        ),
        Check(
            "zswap-compressor",
            zp.compressor == "zstd",
            f"want zstd got {zp.compressor or 'none'}",
            "boot with zswap.compressor=zstd",
        ),
        Check(
            "zswap-pool-cap",
            zp.max_pool_percent == 35,
            f"want 35 got {zp.max_pool_percent if zp.max_pool_percent is not None else 'none'}",
            "boot with zswap.max_pool_percent=35",
        ),
        Check(
            "zswap-shrinker",
            zp.shrinker is not None and zp.shrinker,
            f"shrinker={'Y' if zp.shrinker else 'N' if zp.shrinker is not None else '?'}",
            "boot with zswap.shrinker_enabled=1",
        ),
        Check(
            "zswap-zpool",
            (not zp.zpool_param_exists) or zp.zpool == "zsmalloc",
            zpool_detail,
            None,
        ),
        Check(
            "mglru",
            lru.enabled is not None and (lru.enabled & 7) == 7,
            f"{lru_detail} want 7",
            "kutu-memory-early enables MGLRU at boot",
        ),
        Check(
            "mglru-min-ttl",
            lru.min_ttl_ms == 1000,
            f"want 1000 got {lru.min_ttl_ms if lru.min_ttl_ms is not None else 'none'}",
            "kutu-memory-early sets the anti-thrash window",
        ),
        Check(
            "damon-sysfs",
            (sys / "kernel/mm/damon/admin").is_dir(),
            "presence of the sysfs interface",
            "kernel needs CONFIG_DAMON_SYSFS",
        ),
        Check(
            "psi",
            _file(proc / "pressure/memory"),
            "presence of /proc/pressure/memory",
            "kernel needs CONFIG_PSI",
        ),
        Check(
            "per-cgroup-zswap",
            _file(sys / "fs/cgroup/system.slice/memory.zswap.max"),
            "memory.zswap.max on system.slice",
            "needs cgroup v2 zswap accounting (6.8+)",
        ),
        Check(
            "thp-madvise",
            thp == "madvise",
            f"got {thp or 'none'}",
            "boot with transparent_hugepage=madvise",
        ),
    ]


def service_checks() -> list[Check]:
    checks = []
    for unit in ("systemd-oomd", "kutu-memory-early", "kutu-damon"):
        state = system.service_active(unit)
        checks.append(
            Check(unit, state, "active" if state else "inactive/unavailable",
                  f"systemctl enable --now {unit}")
        )
    return checks


def config_checks() -> list[Check]:
    from . import mode as mode_mod

    current = mode_mod.current_mode()
    total = memory.memtotal_kb()
    recommended = memory.detect_mode(total) if total else None
    return [
        Check(
            "mode-config",
            current in mode_mod.MODES,
            f"MODE={current or 'unset'} in /etc/kutu/memory.conf",
            "run: kutu-doctor mode set <saver|balanced|performance>",
        ),
        Check(
            "mode-recommended",
            None if current is None or recommended is None else current == recommended,
            f"current={current or '?'} recommended-for-this-ram={recommended or '?'}",
            "kutu mode set applies the matching ceilings",
        ),
    ]


def run_all() -> list[Check]:
    return [*kernel_checks(), *service_checks(), *config_checks()]


def failures(checks: list[Check]) -> list[Check]:
    return [c for c in checks if c.ok is False]
