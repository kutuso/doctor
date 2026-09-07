"""In-VM integration check: drives the real kernel through the kutu core modules.

Runs inside a live kutu OS VM (see scripts/vmtest.sh). It asserts the
baseline stack, then mutates real kernel state — zswap pool cap, MGLRU TTL,
DAMON state, live mode ceilings — and verifies the CLI observes every change,
including the systemctl -> cgroupfs round-trip. Stdlib only: the live ISO has
no typer/rich, and the core modules deliberately don't need them.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from kutu_doctor import apps, doctor, memory, mode  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok, detail: str = "") -> None:
    ok = bool(ok)
    RESULTS.append((name, ok, detail))
    print(f"VMTEST:{'PASS' if ok else 'FAIL'}:{name} {detail}", flush=True)


def sh(cmd: str) -> None:
    subprocess.run(cmd, shell=True, check=True)


def failed_kernel_checks() -> set[str]:
    return {c.name for c in doctor.failures(doctor.kernel_checks())}


total = memory.memtotal_kb()
check("meminfo", total and total > 1_000_000, f"MemTotal={total}kB")

zp = memory.zswap_params()
check("zswap-on", zp.enabled is True, f"enabled={zp.enabled}")
check("zswap-zstd", zp.compressor == "zstd", f"compressor={zp.compressor}")
check("zswap-pool-35", zp.max_pool_percent == 35, f"cap={zp.max_pool_percent}")

lru = memory.mglru()
check(
    "mglru",
    lru.enabled == 0x7 and lru.min_ttl_ms == 1000,
    f"enabled={lru.enabled} ttl={lru.min_ttl_ms}",
)
check("damon-on", memory.damon_state() == "on", f"state={memory.damon_state()}")
check("psi", memory.psi_memory() is not None)
high = memory.user_slice_memory_high()
check("user-slice-high", high is not None and high > 0, f"{high}")

check("doctor-kernel-clean", not (failed := failed_kernel_checks()), str(failed))

profiles = {p.name: p for p in apps.list_apps()}
check("apps-profiles", "firefox" in profiles, str(sorted(profiles)))

check(
    "mode-current",
    mode.current_mode() == memory.detect_mode(total),
    f"current={mode.current_mode()} recommended={memory.detect_mode(total)}",
)

sh("echo 20 > /sys/module/zswap/parameters/max_pool_percent")
check("sees-pool-20", memory.zswap_params().max_pool_percent == 20)
check("doctor-catches-pool", "zswap-pool-cap" in failed_kernel_checks())
sh("echo 35 > /sys/module/zswap/parameters/max_pool_percent")
check("sees-pool-restored", memory.zswap_params().max_pool_percent == 35)

sh("echo 500 > /sys/kernel/mm/lru_gen/min_ttl_ms")
check("sees-ttl-500", memory.mglru().min_ttl_ms == 500)
check("doctor-catches-ttl", "mglru-min-ttl" in failed_kernel_checks())
sh("echo 1000 > /sys/kernel/mm/lru_gen/min_ttl_ms")

subprocess.run(["/usr/bin/kutu-damon", "stop"], check=False)
check("sees-damon-off", memory.damon_state() != "on", f"state={memory.damon_state()}")
subprocess.run(["/usr/bin/kutu-damon", "start"], check=False)
check("sees-damon-back", memory.damon_state() == "on", f"state={memory.damon_state()}")

want = total * 1024 * 95 // 100
before = memory.user_slice_memory_high()
mode.set_mode("performance")
dropin = pathlib.Path("/etc/systemd/system/user.slice.d/50-kutu.conf").read_text()
check("mode-dropin-95", f"MemoryHigh={want}" in dropin, dropin.strip())
after = memory.user_slice_memory_high()
check("mode-live-cgroup", after == want, f"{before} -> {after} want {want}")
check("mode-apps-firefox-70", apps.get_app("firefox").memory_high_pct == 70)

mode.set_mode("saver")
saver_want = total * 1024 * 85 // 100
check(
    "mode-restored",
    memory.user_slice_memory_high() == saver_want,
    f"{after} -> {memory.user_slice_memory_high()} want {saver_want}",
)

with open("/tmp/vmcheck.json", "w") as fh:
    json.dump([{"name": n, "ok": ok, "detail": d} for n, ok, d in RESULTS], fh, indent=2)

fails = [n for n, ok, _ in RESULTS if not ok]
print(f"VMTEST:DONE total={len(RESULTS)} fails={len(fails)}", flush=True)
sys.exit(1 if fails else 0)
