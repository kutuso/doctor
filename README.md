# kutu-doctor — the memory-health dashboard for kutu OS

**`kutu-doctor`** is the M2 companion tool for
[kutu OS](https://github.com/kutuso/os) — the RAM-sipping Linux desktop. One
screen shows the whole memory stack live; a handful of commands verify it,
switch modes, inspect per-app ceilings and revert everything to stock.

```
╭─ kutu-doctor ──────────────────────────────────────────────────────╮
│ memory                      │ stack                                 │
│   ram    ━━━━━━━━━ 9.8 GiB/ │   mglru     ● on · ttl 1000 ms        │
│          16.0 GiB           │   damon     on                        │
│   swap  ━ 300.0 MiB/8.0 GiB │   oomd      ● on                      │
│   pressure some ▏0.12% full │   thp       madvise                   │
│          ▏0.00%             │   user.slice  MemoryHigh 14.1 GiB     │
│ zswap                       │   firefox     ceiling 8.0 GiB (50%)   │
│   state  zstd · cap 35% ·   │ top consumers                         │
│          shrinker on        │   user.slice              ━━ 1.5 GiB  │
│   pool   ━━ 512.0 MiB /     │   session-1.scope         ━ 1.1 GiB   │
│          5.6 GiB            │   system.slice            ▏ 200.0 MiB │
│   compression ━ ≈1.0×       │   NetworkManager.service  ▏ 50.0 MiB  │
╰─────────────────────────────┴───────────────────────────────────────╯
```

Live view, refreshed every couple of seconds, until Ctrl-C.

## Commands

| Command | What it does |
|---|---|
| `kutu-doctor` | The live dashboard (same as `dash`). |
| `kutu-doctor dash [-i SECONDS]` | The live memory-health dashboard: RAM/swap bars, PSI gauges, zswap pool + compression ratio, stack states, ceilings and the top cgroup memory consumers. |
| `kutu-doctor status [--json]` | One-shot snapshot of the same data (JSON for scripting). |
| `kutu-doctor check [--json]` | The `kutu-check-kernel` contract in friendlier clothes: verifies every kernel feature and service the stack relies on, with fix hints. Exits non-zero on failures. |
| `kutu-doctor mode` | Shows the current mode and the one recommended for this machine's RAM. |
| `kutu-doctor mode set <mode>` | Persists the mode **and applies its ceilings live** — writes `/etc/kutu/memory.conf`, the `user.slice` drop-in and the app ceilings, then applies them via `systemctl set-property --runtime` (no reboot). Needs root. |
| `kutu-doctor mode apply` | Re-applies the persisted mode (idempotent; useful after editing profiles). |
| `kutu-doctor apps` | Lists the profiles in `/etc/kutu/apps.d` with their effective `MemoryHigh`. |
| `kutu-doctor apps run <profile> <cmd...>` | Runs a command inside its memory-ceiling systemd scope (same semantics as `kutu-run`, unique scope names). |
| `kutu-doctor reset [--yes]` | Runs `kutu-reset` from `kutu-memory`: the whole stack back to stock Arch defaults. |
| `kutu-doctor version` | Version. |

## Modes

The ceiling matrices are **locked by the kutu OS design spec** (§6–§7) — this
tool applies them, it doesn't invent them:

| Mode | Chosen when | user.slice | firefox |
|---|---|---|---|
| `saver` | < 6 GiB | 85% | 40% |
| `balanced` | 6–16 GiB | 90% | 50% |
| `performance` | > 16 GiB | 95% | 70% |

`kutu-doctor mode set` is the user-facing mode switch the OS documentation
promised — it edits exactly the files `kutu-firstboot` writes (`memory.conf`,
the `user.slice` drop-in, `apps.d` ceilings) and then applies them live, so
no reboot is needed. Custom values in non-builtin app profiles are left
untouched.

## Install

On kutu OS it ships as the `kutu-doctor` package (preinstalled). Everywhere
else it's a plain Python package with two runtime dependencies — any Linux
distro with Python ≥ 3.10 works:

```sh
pipx install kutu-doctor        # from PyPI
pipx install git+https://github.com/kutuso/doctor.git   # bleeding edge
```

(Debian/Ubuntu/Fedora: `pipx` via your package manager or pip; the package
itself is pure Python — no compilation, no distro-specific code.)

### Running on non-kutu distros

Nothing is hardcoded to kutu OS or Arch:

- Reads only `/proc` and `/sys` (meminfo, PSI, zswap, MGLRU, DAMON,
  cgroups) — present on any modern mainline kernel regardless of distro.
- `systemctl` calls are for status checks and mode application; on non-
  systemd systems the service probes degrade to `?` and everything else
  still works.
- Without the kutu packages installed: the **dashboard and `status` show
  the kernel-side stack**, `check` tells you exactly what's absent with fix
  hints, `mode set` errors cleanly (no `/etc/kutu` to calibrate), and
  `reset` points you at the kutu repository. Mode switching becomes useful
  as soon as `kutu-memory`/`kutu-base` are installed — on Arch or an
  Arch-derivative that's one pacman.conf stanza away.

That's also why distro coupling was never a problem: kutu OS *vendors* this
repo as a package, but the tool itself only reads standard kernel
interfaces and writes files the kutu packages document.

## Environment overrides

The tool honors the same conventions as the shell tools in kutu OS, which is
also how the test suite fakes a whole machine:

| Variable | Replaces | Used for |
|---|---|---|
| `KUTU_ROOT` | `/` (prefix for `/etc`) | inspect a target/chroot, tests |
| `KUTU_SYSFS` | `/sys` | fake sysfs trees |
| `KUTU_PROC` | `/proc` | fake meminfo/PSI |
| `KUTU_SYSTEMCTL` | `systemctl` | command stubs |
| `KUTU_SYSTEMD_RUN` | `systemd-run` | command stubs |
| `KUTU_DRY_RUN=1` | — | `apps run` prints the command instead of exec'ing |

## Scripting

`status` and `check` emit JSON with `--json`:

```sh
kutu-doctor status --json | jq '.zswap'
kutu-doctor check --json | jq '.checks[] | select(.ok == false)'
```

## Development

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest          # unit tests over a full fake /sys + /proc + /etc tree
ruff check .    # lint
```

The tests never touch the real system — they build a fake kernel tree and
systemctl stubs per test (`tests/conftest.py`), in the spirit of the kutu OS
repo's host-safety rules.

## Integration testing in QEMU

Fakes prove the parsing logic; they can't prove the tool reads a real kernel
or that its writes actually land. For that, boot the real thing:

```sh
make vmtest      # or: scripts/vmtest.sh
```

This boots the latest kutu OS ISO from `../os/out/` (override with
`KUTU_ISO=...`) in QEMU — inside a disposable docker container, KVM when
available — shares this repo into the live VM over 9p, and runs
`scripts/vm_kernel_check.py` against the genuine kernel. It verifies the
baseline stack and then **mutates real state and asserts the tool observes
it**:

- `echo 20 > /sys/module/zswap/parameters/max_pool_percent` → the reader
  sees 20 and `check` flags `zswap-pool-cap`; restored → clean again
- `echo 500 > /sys/kernel/mm/lru_gen/min_ttl_ms` → seen + flagged
- `kutu-damon stop` / `start` → the reader tracks the kdamond state
- `mode.set_mode("performance")` → the `user.slice` drop-in is rewritten,
  `systemctl set-property --runtime` applies it, and
  `/sys/fs/cgroup/user.slice/memory.high` reflects the exact bytes —
  then restores the mode appropriate for the VM's RAM

The VM is disposable, so kernel-state mutation is the point, not a hazard.
CI runs only the unit suite (there is no published ISO artifact yet);
`make vmtest` is the pre-release gate, exactly like `make smoke` in the OS
repo.

## Releases

Tags `vX.Y.Z` build an sdist + wheel and publish to PyPI via
[trusted publishing](https://docs.pypi.org/trusted-publishers/) (workflow:
`.github/workflows/pypi.yml`). One-time maintainer setup: register the
`kutu-doctor` project on PyPI with publisher `kutuso/doctor`, workflow
`pypi.yml`, environment `pypi` — after that every tag publishes
automatically.

## Relationship to kutu OS

- The M2 roadmap item: `kutu-doctor` for live memory-health visibility (the
  PSI-driven `kutu-memoryd` policy daemon is the other half and stays on the
  OS side).
- This repo is the source of truth; the OS distro packages a vendored copy
  (`packages/kutu-doctor/` in kutuso/os). After changing this repo, run
  `make vendor` and bump the package's `pkgrel` over there.
- Reads and writes only files owned by the OS packages (`kutu-base`,
  `kutu-memory`) — nothing else on disk.
- systemd remains the sole cgroup writer: live application goes through
  `systemctl daemon-reload` + `systemctl set-property --runtime`.
- Missing kutu OS pieces degrade gracefully: on a stock Arch box the
  dashboard still shows the kernel-side stack, `check` tells you what's
  absent, and `reset` points you at the kutu repository.

MIT licensed — see [LICENSE](LICENSE).
