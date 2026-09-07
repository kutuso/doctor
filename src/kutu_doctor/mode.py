"""Memory modes: the spec-locked ceiling matrices and their (live) application.

The values are locked by the kutu OS design spec (§6–§7); changing them is a
spec change on the OS side, not a CLI tweak:

=========== ============= ============= =========
mode        chosen when  user.slice    firefox
=========== ============= ============= =========
saver       < 6 GiB      85%           40%
balanced    6–16 GiB     90%           50%
performance > 16 GiB     95%           70%
=========== ============= ============= =========
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from . import paths, system

MODES: dict[str, Mode] = {}


@dataclass(frozen=True)
class Mode:
    name: str
    user_high_pct: int
    app_pct: dict[str, int]

    @property
    def title(self) -> str:
        return {
            "saver": "tighter ceilings, aggressive reclaim",
            "balanced": "the documented defaults",
            "performance": "looser ceilings",
        }[self.name]


MODES["saver"] = Mode("saver", 85, {"firefox": 40})
MODES["balanced"] = Mode("balanced", 90, {"firefox": 50})
MODES["performance"] = Mode("performance", 95, {"firefox": 70})


def current_mode() -> str | None:
    """MODE= from /etc/kutu/memory.conf (the post-firstboot source of truth)."""
    try:
        text = paths.memory_conf().read_text()
    except OSError:
        return None
    for line in text.splitlines():
        match = re.match(r"\s*MODE\s*=\s*(\S+)", line)
        if match:
            return match.group(1)
    return None


def set_mode(name: str, *, apply_live: bool = True, memtotal_kb: int | None = None) -> None:
    """Persist MODE and (by default) apply the ceilings immediately."""
    mode = MODES[name]
    _write_memory_conf(name)
    if apply_live:
        apply_mode(mode, memtotal_kb=memtotal_kb)


def _write_memory_conf(name: str) -> None:
    conf = paths.memory_conf()
    conf.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    replaced = False
    if conf.exists():
        for line in conf.read_text().splitlines():
            if re.match(r"\s*MODE\s*=", line):
                lines.append(f"MODE={name}")
                replaced = True
            else:
                lines.append(line)
    if not replaced:
        lines.append(f"MODE={name}")
    tmp = conf.with_suffix(".conf.tmp")
    tmp.write_text("\n".join(lines).rstrip("\n") + "\n")
    os.replace(tmp, conf)


def apply_mode(mode: Mode, *, memtotal_kb: int | None = None) -> dict[str, int]:
    """Apply a mode's ceilings now and for future boots; returns applied bytes.

    - user.slice: rewrite the firstboot drop-in + ``systemctl set-property
      --runtime`` (systemd remains the sole cgroup writer).
    - app ceilings: update KUTU_MEMORY_HIGH_PCT in matching apps.d profiles;
      custom values in other profiles are left untouched.
    """
    from . import memory

    total = memtotal_kb if memtotal_kb is not None else memory.memtotal_kb()
    if not total:
        raise SystemExit("kutu: cannot read MemTotal; cannot compute ceilings")

    user_high = total * 1024 * mode.user_high_pct // 100
    dropin = paths.user_slice_dropin()
    dropin.parent.mkdir(parents=True, exist_ok=True)
    tmp = dropin.with_suffix(".conf.tmp")
    tmp.write_text(f"[Slice]\nMemoryHigh={user_high}\n")
    os.replace(tmp, dropin)

    app_bytes: dict[str, int] = {}
    apps_dir = paths.apps_dir()
    if apps_dir.is_dir():
        for conf in sorted(apps_dir.glob("*.conf")):
            profile = conf.stem
            pct = mode.app_pct.get(profile)
            if pct is None:
                continue
            _replace_assignment(conf, "KUTU_MEMORY_HIGH_PCT", str(pct))
            app_bytes[profile] = total * 1024 * pct // 100

    system.systemctl("daemon-reload", check=False)
    system.systemctl("set-property", "--runtime", "user.slice", f"MemoryHigh={user_high}")
    return {"user.slice": user_high, **app_bytes}


def _replace_assignment(path, key: str, value: str) -> None:
    text = path.read_text()
    pattern = re.compile(rf"(?m)^(\s*{re.escape(key)}\s*=\s*).*$")
    if pattern.search(text):
        new_text = pattern.sub(rf"\g<1>{value}", text)
    else:
        new_text = text.rstrip("\n") + f"\n{key}={value}\n"
    tmp = path.with_suffix(".conf.tmp")
    tmp.write_text(new_text)
    os.replace(tmp, path)
