from __future__ import annotations

from kutu_doctor import apps


def test_list_apps_parses_profiles(fake_stack):
    profiles = {p.name: p for p in apps.list_apps()}
    assert set(profiles) == {"firefox", "custom"}
    ff = profiles["firefox"]
    assert ff.memory_high_pct == 50
    assert ff.cpu_weight == 100
    assert ff.memory_merge is False


def test_effective_memory_high(fake_stack):
    ff = apps.get_app("firefox")
    assert apps.effective_memory_high(ff, fake_stack["memtotal_kb"]) == (
        fake_stack["memtotal_kb"] * 1024 * 50 // 100
    )
    assert apps.effective_memory_high(ff, None) is None


def test_scope_command_shape_and_uniqueness(fake_stack):
    ff = apps.get_app("firefox")
    cmd = apps.build_scope_command(ff, ["/usr/bin/firefox"], fake_stack["memtotal_kb"])
    assert cmd[0].endswith("systemd-run")
    assert "--user" in cmd and "--scope" in cmd
    assert "--expand-environment=no" in cmd
    assert any(a.startswith("--unit=app-firefox-") for a in cmd)
    assert f"-p MemoryHigh={fake_stack['memtotal_kb'] * 1024 * 50 // 100}" in cmd
    assert "-p CPUWeight=100" in cmd
    assert cmd[cmd.index("--") + 1:] == ["/usr/bin/firefox"]

    cmd2 = apps.build_scope_command(ff, ["/usr/bin/firefox"], fake_stack["memtotal_kb"])
    unit1 = next(a for a in cmd if a.startswith("--unit="))
    unit2 = next(a for a in cmd2 if a.startswith("--unit="))
    assert unit1 != unit2


def test_scope_command_sanitizes_profile_names(fake_stack):
    weird = apps.AppProfile(name="../evil name", memory_high_pct=10)
    cmd = apps.build_scope_command(weird, ["true"], 1000)
    unit = next(a for a in cmd if a.startswith("--unit="))
    assert ".." not in unit and " " not in unit


def test_get_app_missing(fake_stack):
    assert apps.get_app("nope") is None
