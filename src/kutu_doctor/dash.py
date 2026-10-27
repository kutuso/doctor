"""The live memory-health dashboard: one screen, refreshed until you look away."""

from __future__ import annotations

import time

from rich.console import Group, RenderableType
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import memory
from .apps import effective_memory_high
from .render import R2, R4, R5, R6, R7, human_bytes

DASH_TITLE = "kutu-doctor"


def _bar(used: float, total: float, width: int = 22, color: str = R5) -> str:
    if total <= 0:
        return "─" * width
    filled = max(0, min(width, round(used / total * width)))
    return f"[{color}]{'━' * filled}[/][#262637]{'━' * (width - filled)}[/]"


def _kv_table(rows: list[tuple[str, RenderableType]]) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()
    for key, value in rows:
        table.add_row(key, value)
    return table


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value}%"


def _ram_panel(stack: memory.Stack) -> Panel:
    total_b = (stack.memtotal_kb or 0) * 1024
    rows: list[tuple[str, RenderableType]] = []
    if stack.memavailable_kb is None:
        rows.append(("ram", f"[dim]available unknown[/] / {human_bytes(total_b)}"))
    else:
        used_b = total_b - stack.memavailable_kb * 1024
        rows.append(
            ("ram", f"{_bar(used_b, total_b)} {human_bytes(used_b)} / {human_bytes(total_b)}")
        )
    if stack.swaptotal_kb and stack.swapfree_kb is not None:
        swap_used = (stack.swaptotal_kb - stack.swapfree_kb) * 1024
        rows.append(
            (
                "swap",
                f"{_bar(swap_used, stack.swaptotal_kb * 1024, color=R2)} "
                f"{human_bytes(swap_used)} / {human_bytes(stack.swaptotal_kb * 1024)}",
            ),
        )
    if stack.psi:
        some, full = stack.psi.some_avg10, stack.psi.full_avg10
        rows.append(
            (
                "pressure",
                f"some {_bar(some or 0, 100, width=12, color=R7)} {_pct(some)}  "
                f"full {_bar(full or 0, 100, width=12, color=R7)} {_pct(full)}",
            )
        )
    return Panel(_kv_table(rows), title="memory", title_align="left", border_style="#2c2c42")


def _flag(flag: bool | None) -> str:
    return "?" if flag is None else "on" if flag else "off"


def _zswap_panel(stack: memory.Stack) -> Panel:
    z, live = stack.zswap, stack.zswap_live
    rows = [
        (
            "state",
            f"{_flag(z.enabled)} · {z.compressor or '?'} · "
            f"cap {'?' if z.max_pool_percent is None else z.max_pool_percent}% · "
            f"shrinker {_flag(z.shrinker)}",
        ),
    ]
    if live.pool_total_size is not None:
        cap = live.pool_cap_bytes or live.pool_total_size
        rows.append(
            (
                "pool",
                f"{_bar(live.pool_total_size, cap)} {human_bytes(live.pool_total_size)} / "
                f"{human_bytes(cap)}",
            ),
        )
        if live.compressed_ratio:
            rows.append(
                (
                    "compression",
                    f"{_bar(live.compressed_ratio, 4, color=R4)} ≈{live.compressed_ratio:.1f}×",
                ),
            )
    else:
        rows.append(("pool", "[dim]detail needs root (debugfs)[/]"))
    return Panel(_kv_table(rows), title="zswap", title_align="left", border_style="#2c2c42")


def _stack_panel(stack: memory.Stack) -> Panel:
    def state(flag: bool | None) -> str:
        if flag is None:
            return "[dim]?[/]"
        return f"[{R4}]●[/] on" if flag else "[#ff6b6b]●[/] off"

    lru = stack.lru
    lru_on = None if lru.enabled is None else lru.enabled != 0
    ttl = "?" if lru.min_ttl_ms is None else lru.min_ttl_ms
    damon = f"[{R5}]{stack.damon or '?'}[/]" if stack.damon else "[dim]n/a[/]"
    rows = [
        ("mglru", f"{state(lru_on)} · ttl {ttl} ms"),
        ("damon", damon),
        ("oomd", state(stack.oomd_active)),
        ("thp", stack.thp or "?"),
    ]
    if stack.user_high is not None:
        share = ""
        if stack.memtotal_kb:
            share = f" [dim]({stack.user_high * 100 // (stack.memtotal_kb * 1024)}% of ram)[/]"
        rows.append(("user.slice", f"MemoryHigh {human_bytes(stack.user_high)}{share}"))
    for app in _apps():
        high = effective_memory_high(app, stack.memtotal_kb)
        pct = f" [dim]({app.memory_high_pct}%)[/]" if app.memory_high_pct else ""
        ceiling = f"ceiling {human_bytes(high)}{pct}" if high else "no ceiling"
        rows.append((f"[{R6}]{escape(app.name)}[/]", ceiling))
    return Panel(_kv_table(rows), title="stack", title_align="left", border_style="#2c2c42")


def _short_cgroup(name: str, limit: int = 32) -> str:
    if len(name) <= limit:
        return name
    parts = name.split("/")
    short = "/".join(parts[-2:]) if len(parts) > 1 else name
    if len(short) <= limit:
        return f"…/{short}"
    return f"…{short[-(limit - 1):]}"


def _top_panel(top: list[tuple[str, int]]) -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column()
    table.add_column()
    if not top:
        table.add_row("", "[dim]no cgroup memory data[/]", "")
    peak = top[0][1] if top else 1
    for name, current in top:
        bar = _bar(current, peak, width=16, color=R2)
        table.add_row(f"[{R5}]{escape(_short_cgroup(name))}[/]", bar, human_bytes(current))
    return Panel(table, title="top consumers", title_align="left", border_style="#2c2c42")


def _apps():
    from . import apps as apps_mod

    return apps_mod.list_apps()


def build_frame(*, services: bool = True) -> RenderableType:
    stack = memory.gather(include_services=services)
    top = memory.top_cgroups()
    title = Text.assemble(
        (DASH_TITLE, f"bold {R6}"),
        ("  ·  ", "dim"),
        (f"mode {stack.mode or 'unset'}", R2),
        (f"  ·  ram {human_bytes((stack.memtotal_kb or 0) * 1024)}", "dim"),
    )
    left = Group(_ram_panel(stack), _zswap_panel(stack))
    right = Group(_stack_panel(stack), _top_panel(top))
    columns = Table.grid(padding=(0, 1))
    columns.add_column(ratio=1)
    columns.add_column(ratio=1)
    columns.add_row(left, right)
    return Group(title, Text(""), columns, Text(""))


def run(interval: float = 2.0, services: bool = True) -> None:
    from rich.console import Console

    console = Console()
    if not console.is_terminal:
        console.print(build_frame(services=services))
        return
    try:
        with Live(build_frame(services=services), console=console, screen=False) as live:
            while True:
                time.sleep(interval)
                live.update(build_frame(services=services))
    except KeyboardInterrupt:
        console.print(f"\n[{R4}]kutu-doctor:[/] stay healthy\n")


__all__ = ["DASH_TITLE", "build_frame", "run"]
