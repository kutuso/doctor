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
    high = fake_stack["memtotal_kb"] * 1024 * 50 // 100
    assert cmd[cmd.index("-p") + 1] == f"MemoryHigh={high}"
    assert cmd[cmd.index("-p", cmd.index("-p") + 1) + 1] == "CPUWeight=100"
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


def test_profile_names_reject_traversal(fake_stack):
    assert apps.get_app("../evil") is None
    assert apps.get_app("sub/dir") is None
    assert apps.get_app("") is None
    assert apps.get_app(".hidden") is None
    assert apps.valid_profile_name("firefox-11.x_2") is True


def test_profile_parsing_matches_kutu_run_shell_semantics(fake_stack):
    conf = fake_stack["etc"] / "kutu/apps.d/shellstyle.conf"
    conf.write_text(
        'KUTU_MEMORY_HIGH_PCT="50"  # quoted with a comment\n'
        "KUTU_CPU_WEIGHT='80'\n"
        "KUTU_MEMORY_SWAP_MAX=2G\n"
        "KUTU_MEMORY_MERGE=1\n"
    )
    profile = apps.get_app("shellstyle")
    assert profile.memory_high_pct == 50
    assert profile.cpu_weight == 80
    assert profile.memory_swap_max == "2G"
    assert profile.memory_merge is True
    assert profile.invalid == []


def test_profile_parsing_flags_unsafe_values(fake_stack):
    conf = fake_stack["etc"] / "kutu/apps.d/bad.conf"
    conf.write_text("KUTU_MEMORY_HIGH_PCT=500\nKUTU_CPU_WEIGHT=0\nKUTU_MEMORY_SWAP_MAX=\n")
    profile = apps.get_app("bad")
    assert profile.memory_high_pct is None
    assert profile.cpu_weight is None
    expected = ["KUTU_CPU_WEIGHT", "KUTU_MEMORY_HIGH_PCT", "KUTU_MEMORY_SWAP_MAX"]
    assert sorted(profile.invalid) == expected
