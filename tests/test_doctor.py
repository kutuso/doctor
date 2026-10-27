from __future__ import annotations

from kutu_doctor import doctor


def test_all_checks_pass_on_healthy_tree(fake_stack):
    checks = doctor.run_all()
    failed = doctor.failures(checks)
    assert not failed, [(c.name, c.detail) for c in failed]


def test_wrong_pool_cap_fails(fake_stack):
    (fake_stack["sys"] / "module/zswap/parameters/max_pool_percent").write_text("20")
    failed = {c.name for c in doctor.failures(doctor.run_all())}
    assert "zswap-pool-cap" in failed


def test_wrong_min_ttl_fails(fake_stack):
    (fake_stack["sys"] / "kernel/mm/lru_gen/min_ttl_ms").write_text("0")
    failed = {c.name for c in doctor.failures(doctor.run_all())}
    assert "mglru-min-ttl" in failed


def test_damon_disabled_fails(fake_stack):
    import shutil

    shutil.rmtree(fake_stack["sys"] / "kernel/mm/damon/admin")
    failed = {c.name for c in doctor.failures(doctor.run_all())}
    assert "damon-sysfs" in failed


def test_mode_mismatch_is_informational(fake_stack):
    (fake_stack["etc"] / "kutu/memory.conf").write_text("MODE=saver\n")
    checks = {c.name: c for c in doctor.run_all()}
    assert checks["mode-recommended"].ok is not False
    assert "informational" in checks["mode-recommended"].detail
    assert checks["mode-config"].ok is True
    assert not doctor.failures(list(checks.values()))


def test_unknown_mode_config_fails(fake_stack):
    (fake_stack["etc"] / "kutu/memory.conf").write_text("MODE=turbo\n")
    checks = {c.name: c for c in doctor.run_all()}
    assert checks["mode-config"].ok is False


def test_unreachable_systemd_is_indeterminate(fake_stack, monkeypatch):
    monkeypatch.setenv("KUTU_SYSTEMCTL", "/nonexistent/systemctl")
    checks = doctor.run_all()
    assert not doctor.failures(checks)
    unknown = {c.name for c in doctor.indeterminate(checks)}
    assert {"systemd-oomd", "kutu-memory-early", "kutu-damon"} <= unknown


def test_damon_needs_the_kdamonds_interface(fake_stack):
    (fake_stack["sys"] / "kernel/mm/damon/admin/kdamonds/nr_kdamonds").unlink()
    failed = {c.name for c in doctor.failures(doctor.run_all())}
    assert "damon-sysfs" in failed


def test_unreadable_sysfs_directory_is_indeterminate_not_a_crash(fake_stack):
    import os

    import pytest

    if os.geteuid() == 0:
        pytest.skip("permission bits do not bind root")
    blocked = fake_stack["sys"] / "kernel/mm/damon"
    blocked.chmod(0)
    try:
        checks = {c.name: c for c in doctor.run_all()}
    finally:
        blocked.chmod(0o755)
    assert checks["damon-sysfs"].ok is None
