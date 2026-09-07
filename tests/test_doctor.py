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


def test_mode_mismatch_is_a_check(fake_stack):
    (fake_stack["etc"] / "kutu/memory.conf").write_text("MODE=saver\n")
    checks = {c.name: c for c in doctor.run_all()}
    assert checks["mode-recommended"].ok is False
    assert checks["mode-config"].ok is True
