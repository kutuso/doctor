"""The kutu-doctor command: dashboard, status, check, mode, apps and reset."""

from __future__ import annotations

import json as jsonlib
import os
import shutil
from pathlib import Path

import typer
from rich.console import Console

from . import __version__, memory, paths, render, system
from . import apps as apps_mod
from . import dash as dash_module
from . import doctor as doctor_mod
from . import mode as mode_mod

app = typer.Typer(
    help="kutu-doctor: live memory-health dashboard and control for kutu OS.",
    no_args_is_help=False,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
mode_app = typer.Typer(
    help="Show or change the memory mode (saver/balanced/performance).",
    invoke_without_command=True,
)
apps_app = typer.Typer(
    help="List per-app ceiling profiles or run a command in one.",
    invoke_without_command=True,
)
app.add_typer(mode_app, name="mode")
app.add_typer(apps_app, name="apps")

console = Console()
err_console = Console(stderr=True)

MODE_ARGUMENT = typer.Argument(help="saver | balanced | performance")


def _print_json(payload: dict) -> None:
    console.print_json(jsonlib.dumps(payload))


@app.callback()
def _default(ctx: typer.Context) -> None:
    """With no subcommand, kutu-doctor shows the live dashboard."""
    if ctx.invoked_subcommand is None:
        dash_module.run()


@app.command()
def dash(
    interval: float = typer.Option(2.0, "--interval", "-i", min=0.5, help="refresh seconds"),
    services: bool = typer.Option(True, "--services/--no-services", help="probe systemd units"),
) -> None:
    """The live memory-health dashboard (Ctrl-C to exit)."""
    dash_module.run(interval=interval, services=services)


@app.command()
def status(
    as_json: bool = typer.Option(False, "--json", help="emit machine-readable JSON"),
    services: bool = typer.Option(True, "--services/--no-services", help="probe systemd units"),
) -> None:
    """One glance at the whole memory stack."""
    stack = memory.gather(include_services=services)
    profiles = apps_mod.list_apps()
    if as_json:
        _print_json(render.stack_to_json(stack, profiles))
        return
    console.print()
    title = "kutu-doctor — memory stack"
    if stack.mode:
        title += f"  [dim]·[/]  mode [{render.R6}]{stack.mode}[/]"
    console.print(f"[bold]{title}[/]\n")
    console.print(render.status_table(stack, profiles))
    console.print()


@app.command()
def check(
    as_json: bool = typer.Option(False, "--json", help="emit machine-readable JSON"),
) -> None:
    """Verify every feature the memory stack relies on (like kutu-check-kernel)."""
    checks = doctor_mod.run_all()
    failed = doctor_mod.failures(checks)
    if as_json:
        _print_json(
            {
                "checks": [
                    {"name": c.name, "ok": c.ok, "detail": c.detail, "hint": c.hint}
                    for c in checks
                ],
                "failed": len(failed),
            }
        )
    else:
        console.print()
        table, _ = render.doctor_table(checks)
        console.print(table)
        console.print()
        if failed:
            for check in failed:
                if check.hint:
                    err_console.print(f"hint [{check.name}]: {check.hint}")
            console.print(f"[#ff6b6b]{len(failed)} check(s) failed[/]")
        else:
            console.print(f"[{render.R4}]all checks passed[/]")
    raise SystemExit(1 if failed else 0)


@mode_app.callback()
def mode_default(ctx: typer.Context) -> None:
    """Show the current and recommended mode."""
    if ctx.invoked_subcommand is not None:
        return
    current = mode_mod.current_mode()
    total = memory.memtotal_kb()
    recommended = memory.detect_mode(total) if total else None
    table = render.status_table(memory.gather(include_services=False), apps_mod.list_apps())
    label = f"[{render.R6}]{current or 'unset'}[/]"
    if recommended and current != recommended:
        label += f"  [dim](recommended for this RAM: [{render.R2}]{recommended}[/])[/]"
    console.print(f"\ncurrent mode: {label}\n")
    console.print(table)
    console.print("\n[dim]change with:[/] kutu-doctor mode set <saver|balanced|performance>\n")


@mode_app.command("set")
def mode_set(
    name: str = MODE_ARGUMENT,
    live: bool = typer.Option(True, "--live/--no-live", help="apply ceilings now (needs root)"),
) -> None:
    """Persist a mode and apply its ceilings immediately."""
    if name not in mode_mod.MODES:
        err_console.print(
            f"kutu-doctor: unknown mode '{name}' (expected: {' | '.join(mode_mod.MODES)})"
        )
        raise SystemExit(2)
    if live:
        system.require_root(f"mode set {name}")
    mode_mod.set_mode(name, apply_live=live)
    mode_info = mode_mod.MODES[name]
    console.print(
        f"[{render.R4}]mode set:[/] [{render.R6}]{name}[/] "
        f"({mode_info.title}; user.slice {mode_info.user_high_pct}%, "
        f"firefox {mode_info.app_pct.get('firefox')}%)"
    )
    if not live:
        console.print("[dim]config only; ceilings change on next firstboot/apply[/]")


@mode_app.command("apply")
def mode_apply() -> None:
    """Re-apply the persisted mode's ceilings (idempotent)."""
    system.require_root("mode apply")
    current = mode_mod.current_mode()
    if current not in mode_mod.MODES:
        root = os.environ.get("KUTU_ROOT", "")
        err_console.print(f"kutu-doctor: no valid MODE in {root}/etc/kutu/memory.conf")
        raise SystemExit(2)
    applied_now = mode_mod.apply_mode(mode_mod.MODES[current])
    for unit, value in applied_now.items():
        console.print(f"[{render.R4}]applied[/] {unit}: MemoryHigh={render.human_bytes(value)}")


@apps_app.callback()
def apps_default(ctx: typer.Context) -> None:
    """List per-app ceiling profiles."""
    if ctx.invoked_subcommand is not None:
        return
    profiles = apps_mod.list_apps()
    if not profiles:
        console.print("[dim]no profiles in /etc/kutu/apps.d[/]")
        return
    total = memory.memtotal_kb()
    console.print()
    for i, profile in enumerate(profiles):
        color = render.RAINBOW[i % len(render.RAINBOW)]
        high = apps_mod.effective_memory_high(profile, total)
        line = f"MemoryHigh {render.human_bytes(high)}"
        if profile.memory_high_pct is not None:
            line += f" ({profile.memory_high_pct}%)"
        extras = []
        if profile.cpu_weight is not None:
            extras.append(f"cpu {profile.cpu_weight}")
        if profile.memory_swap_max is not None:
            extras.append(f"swap-max {profile.memory_swap_max}")
        if profile.memory_merge:
            extras.append("merge")
        if extras:
            line += f" [dim]· {' · '.join(extras)}[/]"
        console.print(f"[{color}]{profile.name:<14}[/] {line}")
    console.print("\n[dim]run with:[/] kutu-doctor apps run <profile> <command...>\n")


@apps_app.command("run")
def apps_run(
    profile: str = typer.Argument(help="profile name from /etc/kutu/apps.d"),
    cmd: list[str] = typer.Argument(help="command (and arguments) to run"),
) -> None:
    """Run a command inside its memory-ceiling scope (like kutu-run)."""
    if not cmd:
        err_console.print("kutu-doctor: no command given")
        raise SystemExit(2)
    app_profile = apps_mod.get_app(profile)
    if app_profile is None:
        err_console.print(f"kutu-doctor: no profile '{profile}' in /etc/kutu/apps.d")
        raise SystemExit(2)
    argv = apps_mod.build_scope_command(app_profile, list(cmd), memory.memtotal_kb())
    if os.environ.get("KUTU_DRY_RUN") == "1":
        console.print(" ".join(argv), soft_wrap=True, markup=False)
        return
    os.execvp(argv[0], argv)


@app.command()
def reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="skip the confirmation prompt"),
) -> None:
    """Return the memory stack to stock Arch behavior (runs kutu-reset)."""
    binary = shutil.which("kutu-reset") or str(
        Path(os.environ.get("KUTU_ROOT", "/")) / "usr/bin/kutu-reset"
    )
    if not (os.path.isfile(binary) and os.access(binary, os.X_OK)):
        err_console.print(
            "kutu-doctor: kutu-reset not found — is kutu-memory installed? "
            "(https://kutuso.github.io/os/repo/x86_64/)"
        )
        raise SystemExit(1)
    if not yes and not paths.is_sandboxed():
        apply_it = typer.confirm(
            "Revert all kutu memory tuning to stock Arch defaults and reboot later?"
        )
        if not apply_it:
            raise typer.Abort()
    os.execv(binary, [binary])


@app.command()
def version() -> None:
    """Print the kutu-doctor version."""
    console.print(f"kutu-doctor {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
