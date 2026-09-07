"""Filesystem locations, overridable for tests and chroot-style inspection.

The environment variables mirror the conventions of the shell tools shipped in
kutu OS (``kutu-check-kernel``, ``kutu-firstboot``, ``kutu-run``):

- ``KUTU_ROOT``    prefix for ``/etc`` (target inspection, tests)
- ``KUTU_SYSFS``   replacement for ``/sys``
- ``KUTU_PROC``    replacement for ``/proc``
- ``KUTU_SYSTEMCTL``     replacement ``systemctl`` command (tests: stub)
- ``KUTU_SYSTEMD_RUN``   replacement ``systemd-run`` command (tests: stub)
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path


def root() -> Path:
    return Path(os.environ.get("KUTU_ROOT", ""))


def sysfs() -> Path:
    return Path(os.environ.get("KUTU_SYSFS", "/sys"))


def proc() -> Path:
    return Path(os.environ.get("KUTU_PROC", "/proc"))


def etc() -> Path:
    return root() / "etc"


def apps_dir() -> Path:
    return etc() / "kutu" / "apps.d"


def memory_conf() -> Path:
    return etc() / "kutu" / "memory.conf"


def user_slice_dropin() -> Path:
    return root() / "etc/systemd/system/user.slice.d/50-kutu.conf"


def systemctl_cmd() -> list[str]:
    return shlex.split(os.environ.get("KUTU_SYSTEMCTL", "systemctl"))


def systemd_run_cmd() -> list[str]:
    return shlex.split(os.environ.get("KUTU_SYSTEMD_RUN", "systemd-run"))


def is_sandboxed() -> bool:
    return bool(os.environ.get("KUTU_ROOT"))
