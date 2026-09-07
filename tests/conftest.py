"""Shared fixtures: a fake /sys, /proc and /etc tree plus systemctl/systemd-run stubs."""

from __future__ import annotations

import pathlib
import textwrap

import pytest

MEMTOTAL_16G_KB = 16 * 1024 * 1024


def build_kernel_tree(sysroot: pathlib.Path, procroot: pathlib.Path, *, pool_pct: int = 35) -> None:
    zswap = sysroot / "module/zswap/parameters"
    zswap.mkdir(parents=True)
    (zswap / "enabled").write_text("Y")
    (zswap / "compressor").write_text("zstd")
    (zswap / "max_pool_percent").write_text(str(pool_pct))
    (zswap / "shrinker_enabled").write_text("Y")

    lru = sysroot / "kernel/mm/lru_gen"
    lru.mkdir(parents=True)
    (lru / "enabled").write_text("0x0007")
    (lru / "min_ttl_ms").write_text("1000")

    (sysroot / "kernel/mm/damon/admin/kdamonds/0").mkdir(parents=True)
    (sysroot / "kernel/mm/damon/admin/kdamonds/0/state").write_text("on")

    (sysroot / "kernel/mm/transparent_hugepage").mkdir(parents=True)
    (sysroot / "kernel/mm/transparent_hugepage/enabled").write_text(
        "always madvise [madvise] never"
    )

    (sysroot / "fs/cgroup/system.slice").mkdir(parents=True)
    (sysroot / "fs/cgroup/system.slice/memory.zswap.max").write_text("max")
    (sysroot / "fs/cgroup/system.slice/memory.current").write_text(str(200 * 1024 * 1024))
    (sysroot / "fs/cgroup/system.slice/NetworkManager.service").mkdir(parents=True)
    (sysroot / "fs/cgroup/system.slice/NetworkManager.service/memory.current").write_text(
        str(50 * 1024 * 1024)
    )
    (sysroot / "fs/cgroup/user.slice").mkdir(parents=True)
    (sysroot / "fs/cgroup/user.slice/memory.high").write_text("15118201733")
    (sysroot / "fs/cgroup/user.slice/memory.current").write_text(str(1536 * 1024 * 1024))
    (sysroot / "fs/cgroup/user.slice/session-1.scope").mkdir(parents=True)
    (sysroot / "fs/cgroup/user.slice/session-1.scope/memory.current").write_text(
        str(1200 * 1024 * 1024)
    )

    debug = sysroot / "kernel/debug/zswap"
    debug.mkdir(parents=True)
    (debug / "pool_total_size").write_text(str(512 * 1024 * 1024))
    (debug / "stored_pages").write_text(str(131072))
    (debug / "same_filled_pages").write_text("4096")

    procroot.mkdir(parents=True, exist_ok=True)
    (procroot / "meminfo").write_text(
        textwrap.dedent(
            f"""\
            MemTotal:       {MEMTOTAL_16G_KB} kB
            MemFree:        8388608 kB
            MemAvailable:   10485760 kB
            SwapTotal:       8388608 kB
            SwapFree:        8075264 kB
            """
        )
    )
    (procroot / "pressure").mkdir(parents=True, exist_ok=True)
    (procroot / "pressure/memory").write_text(
        "some avg10=0.12 avg60=0.10 avg300=0.08 total=123456\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=100\n"
    )


def build_etc(etcroot: pathlib.Path) -> None:
    (etcroot / "kutu/apps.d").mkdir(parents=True)
    (etcroot / "kutu/memory.conf").write_text("MODE=balanced\n")
    (etcroot / "kutu/apps.d/firefox.conf").write_text(
        "KUTU_MEMORY_HIGH_PCT=50\nKUTU_CPU_WEIGHT=100\n"
    )
    (etcroot / "kutu/apps.d/custom.conf").write_text("KUTU_MEMORY_HIGH_PCT=33\n")
    (etcroot / "systemd/system/user.slice.d").mkdir(parents=True)
    (etcroot / "systemd/system/user.slice.d/50-kutu.conf").write_text(
        f"[Slice]\nMemoryHigh={MEMTOTAL_16G_KB * 1024 * 90 // 100}\n"
    )


@pytest.fixture
def fake_stack(tmp_path, monkeypatch):
    sysroot = tmp_path / "sys"
    procroot = tmp_path / "proc"
    etcroot = tmp_path / "root/etc"
    build_kernel_tree(sysroot, procroot)
    build_etc(etcroot)

    stubs = tmp_path / "bin"
    stubs.mkdir()
    log = tmp_path / "systemctl.log"
    systemctl = stubs / "systemctl"
    systemctl.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            echo "$@" >> {log}
            case "$1" in
              is-active) echo active; exit 0 ;;
              *) exit 0 ;;
            esac
            """
        )
    )
    systemctl.chmod(0o755)
    systemd_run = stubs / "systemd-run"
    systemd_run.write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
    systemd_run.chmod(0o755)

    monkeypatch.setenv("KUTU_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("KUTU_SYSFS", str(sysroot))
    monkeypatch.setenv("KUTU_PROC", str(procroot))
    monkeypatch.setenv("KUTU_SYSTEMCTL", str(systemctl))
    monkeypatch.setenv("KUTU_SYSTEMD_RUN", str(systemd_run))
    return {
        "tmp": tmp_path,
        "sys": sysroot,
        "proc": procroot,
        "etc": etcroot,
        "log": log,
        "memtotal_kb": MEMTOTAL_16G_KB,
    }
