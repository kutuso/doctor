from __future__ import annotations

from kutu_doctor import mode


def test_current_mode(fake_stack):
    assert mode.current_mode() == "balanced"


def test_set_mode_persists_and_applies(fake_stack):
    mode.set_mode("saver")
    assert mode.current_mode() == "saver"
    conf = (fake_stack["etc"] / "kutu/memory.conf").read_text()
    assert "MODE=saver" in conf

    dropin = (fake_stack["etc"] / "systemd/system/user.slice.d/50-kutu.conf").read_text()
    total = fake_stack["memtotal_kb"]
    assert f"MemoryHigh={total * 1024 * 85 // 100}" in dropin

    firefox = (fake_stack["etc"] / "kutu/apps.d/firefox.conf").read_text()
    assert "KUTU_MEMORY_HIGH_PCT=40" in firefox
    assert "KUTU_CPU_WEIGHT=100" in firefox

    custom = (fake_stack["etc"] / "kutu/apps.d/custom.conf").read_text()
    assert "KUTU_MEMORY_HIGH_PCT=33" in custom

    log = fake_stack["log"].read_text()
    assert "daemon-reload" in log
    assert "set-property --runtime user.slice MemoryHigh=" in log


def test_set_mode_config_only(fake_stack):
    mode.set_mode("performance", apply_live=False)
    assert mode.current_mode() == "performance"
    dropin = (fake_stack["etc"] / "systemd/system/user.slice.d/50-kutu.conf").read_text()
    assert "90" not in dropin.split("MemoryHigh=")[1] or "95" in dropin


def test_set_mode_preserves_foreign_lines(fake_stack):
    conf = fake_stack["etc"] / "kutu/memory.conf"
    conf.write_text("# tuned by admin\nMODE=balanced\nEXTRA=keepme\n")
    mode.set_mode("saver", apply_live=False)
    text = conf.read_text()
    assert "# tuned by admin" in text
    assert "EXTRA=keepme" in text
    assert "MODE=saver" in text


def test_apply_mode_updates_each_ceiling(fake_stack):
    applied = mode.apply_mode(mode.MODES["performance"])
    total = fake_stack["memtotal_kb"]
    assert applied["user.slice"] == total * 1024 * 95 // 100
    assert applied["firefox"] == total * 1024 * 70 // 100


def test_current_mode_strips_quotes_and_last_assignment_wins(fake_stack):
    conf = fake_stack["etc"] / "kutu/memory.conf"
    conf.write_text('MODE=saver\nMODE="performance"  # tuned\n')
    assert mode.current_mode() == "performance"
    conf.write_text("MODE='balanced'\n")
    assert mode.current_mode() == "balanced"


def test_current_mode_tolerates_undecodable_conf(fake_stack):
    (fake_stack["etc"] / "kutu/memory.conf").write_bytes(b"\xff\xfe MODE=saver\n")
    assert mode.current_mode() is None


def test_written_files_stay_world_readable_under_strict_umask(fake_stack):
    import os
    import stat

    old = os.umask(0o077)
    try:
        mode.set_mode("saver")
    finally:
        os.umask(old)
    for rel in (
        "kutu/memory.conf",
        "systemd/system/user.slice.d/50-kutu.conf",
        "kutu/apps.d/firefox.conf",
    ):
        assert stat.S_IMODE((fake_stack["etc"] / rel).stat().st_mode) == 0o644


def test_set_mode_without_memtotal_leaves_config_untouched(fake_stack, monkeypatch, tmp_path):
    import pytest

    empty = tmp_path / "emptyproc"
    empty.mkdir()
    monkeypatch.setenv("KUTU_PROC", str(empty))
    with pytest.raises(SystemExit):
        mode.set_mode("saver")
    assert mode.current_mode() == "balanced"
