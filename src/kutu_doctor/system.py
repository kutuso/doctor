"""Systemd interaction helpers; systemctl stays the only writer of cgroup state."""

from __future__ import annotations

import subprocess

from . import paths


class RunError(RuntimeError):
    def __init__(self, cmd: list[str], returncode: int, output: str) -> None:
        super().__init__(f"command failed ({returncode}): {' '.join(cmd)}\n{output}")
        self.cmd = cmd
        self.returncode = returncode
        self.output = output


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RunError(cmd, proc.returncode, (proc.stdout + proc.stderr).strip())
    return proc


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run([*paths.systemctl_cmd(), *args], check=check)


def service_active(name: str) -> bool | None:
    """True/False for known states, None when systemctl is unavailable."""
    try:
        proc = systemctl("is-active", name, check=False)
    except (FileNotFoundError, PermissionError, OSError):
        return None
    state = proc.stdout.strip()
    if state == "active":
        return True
    if state in {"inactive", "failed", "activating", "deactivating"}:
        return False
    return None


def require_root(action: str) -> None:
    """Refuse mutating actions unless root; sandboxed (KUTU_ROOT) runs skip the check."""
    import os
    import sys

    if paths.is_sandboxed():
        return
    if os.geteuid() != 0:
        print(f"kutu: {action} requires root (try: sudo kutu ...)", file=sys.stderr)
        raise SystemExit(1)
