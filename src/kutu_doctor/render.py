"""Human and JSON rendering for the kutu CLI."""

from __future__ import annotations

from typing import Any

from rich.table import Table

from . import memory
from .apps import effective_memory_high

R1, R2, R3, R4, R5, R6, R7 = (
    "#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF", "#D4BAFF", "#FFB3E6",
)
RAINBOW = [R1, R2, R3, R4, R5, R6, R7]


def human_bytes(n: int | float | None) -> str:
    if n is None:
        return "n/a"
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TiB"


def _yn(flag: bool | None) -> str:
    if flag is None:
        return "[dim]?[/dim]"
    return f"[{R4}]on[/]" if flag else "[#ff6b6b]off[/]"


def _num(value, default: str = "n/a") -> str:
    return default if value is None else str(value)


def stack_to_json(stack: memory.Stack, apps: list) -> dict[str, Any]:
    mi = {
        "memtotal_kb": stack.memtotal_kb,
        "memavailable_kb": stack.memavailable_kb,
        "swaptotal_kb": stack.swaptotal_kb,
        "swapfree_kb": stack.swapfree_kb,
    }
    out: dict[str, Any] = {
        "meminfo": mi,
        "mode": {"current": stack.mode, "recommended": stack.recommended_mode},
        "zswap": {
            "enabled": stack.zswap.enabled,
            "compressor": stack.zswap.compressor,
            "max_pool_percent": stack.zswap.max_pool_percent,
            "shrinker": stack.zswap.shrinker,
            "zpool": stack.zswap.zpool,
            "zpool_param_exists": stack.zswap.zpool_param_exists,
            "pool_total_size": stack.zswap_live.pool_total_size,
            "stored_pages": stack.zswap_live.stored_pages,
            "pool_cap_bytes": stack.zswap_live.pool_cap_bytes,
            "compressed_ratio": (
                round(stack.zswap_live.compressed_ratio, 2)
                if stack.zswap_live.compressed_ratio
                else None
            ),
        },
        "mglru": {"enabled": stack.lru.enabled, "min_ttl_ms": stack.lru.min_ttl_ms},
        "damon": stack.damon,
        "oomd_active": stack.oomd_active,
        "psi": {
            "some_avg10": stack.psi.some_avg10 if stack.psi else None,
            "full_avg10": stack.psi.full_avg10 if stack.psi else None,
        },
        "user_slice_memory_high": stack.user_high,
        "thp": stack.thp,
        "apps": [
            {
                "name": app.name,
                "memory_high_pct": app.memory_high_pct,
                "effective_memory_high": effective_memory_high(app, stack.memtotal_kb),
                "cpu_weight": app.cpu_weight,
                "memory_swap_max": app.memory_swap_max,
                "memory_merge": app.memory_merge,
            }
            for app in apps
        ],
    }
    return out


def status_table(stack: memory.Stack, apps: list) -> Table:
    from .apps import effective_memory_high

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()

    mode_line = f"[{R6}]{stack.mode or 'unset'}[/]"
    if stack.recommended_mode and stack.mode != stack.recommended_mode:
        mode_line += f"  [dim](recommended for this RAM: [{R2}]{stack.recommended_mode}[/])[/]"
    table.add_row("mode", mode_line)

    if stack.memtotal_kb:
        ram = (
            f"{human_bytes(stack.memtotal_kb * 1024)} total · "
            f"{human_bytes((stack.memavailable_kb or 0) * 1024)} available"
        )
        if stack.swaptotal_kb:
            used = stack.swaptotal_kb - (stack.swapfree_kb or 0)
            ram += (
                f" · swap {human_bytes(used * 1024)} / {human_bytes(stack.swaptotal_kb * 1024)}"
            )
        table.add_row("ram", ram)

    z = stack.zswap
    zline = (
        f"{_yn(z.enabled)} · {_num(z.compressor)} · pool cap {_num(z.max_pool_percent)}%"
    )
    live = stack.zswap_live
    if live.pool_total_size is not None:
        cap = live.pool_cap_bytes
        zline += (
            f" · pool {human_bytes(live.pool_total_size)}"
            + (f" / {human_bytes(cap)}" if cap else "")
        )
        if live.compressed_ratio:
            zline += f" · ≈{live.compressed_ratio:.1f}× compression"
    else:
        zline += " · [dim]pool detail needs root (debugfs)[/]"
    table.add_row("zswap", zline)

    lru = stack.lru
    table.add_row(
        "mglru",
        f"{_yn(lru.enabled not in (None, 0))} · min_ttl {_num(lru.min_ttl_ms)} ms",
    )
    table.add_row("damon", f"[{R5}]{_num(stack.damon)}[/]")
    table.add_row("oomd", _yn(stack.oomd_active))
    if stack.psi:
        table.add_row(
            "psi mem",
            f"some {_num(stack.psi.some_avg10)} / full {_num(stack.psi.full_avg10)} (avg10)",
        )
    table.add_row("thp", _num(stack.thp))

    if stack.user_high is not None:
        table.add_row("user.slice", f"MemoryHigh {human_bytes(stack.user_high)}")

    for i, app in enumerate(apps):
        color = RAINBOW[i % len(RAINBOW)]
        pct = f" ({app.memory_high_pct}%)" if app.memory_high_pct else ""
        high = effective_memory_high(app, stack.memtotal_kb)
        line = f"MemoryHigh {human_bytes(high)}{pct}" if high else "no ceiling"
        table.add_row(f"[{color}]{app.name}[/]", line)

    return table


def doctor_table(checks) -> tuple[Table, int]:
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(style="dim", no_wrap=False)
    table.add_column()
    failed = 0
    for check in checks:
        if check.ok is False:
            mark, color = "FAIL", "#ff6b6b"
            failed += 1
        elif check.ok is None:
            mark, color = "WARN", R2
        else:
            mark, color = "PASS", R4
        table.add_row(f"[{color}]{mark}[/]", check.name, check.detail)
    return table, failed
