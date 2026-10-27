from __future__ import annotations

from rich.console import Console

from kutu_doctor import dash, memory


def test_top_cgroups_sorted(fake_stack):
    top = memory.top_cgroups()
    names = [name for name, _ in top]
    assert names[0] == "user.slice/session-1.scope"
    assert "user.slice" in names
    assert "system.slice" in names
    values = [value for _, value in top]
    assert values == sorted(values, reverse=True)
    by_name = dict(top)
    total = fake_stack["memtotal_kb"]
    assert by_name["user.slice/session-1.scope"] == 1200 * 1024 * 1024
    assert by_name["user.slice"] == (1536 - 1200) * 1024 * 1024
    assert by_name["system.slice/NetworkManager.service"] == 50 * 1024 * 1024
    assert by_name["system.slice"] == (200 - 50) * 1024 * 1024
    assert total > 0


def test_top_cgroups_reaches_nested_user_scopes(fake_stack):
    deep = fake_stack["sys"] / "fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice"
    app = deep / "app-firefox-123.scope"
    app.mkdir(parents=True)
    (app / "memory.current").write_text(str(1400 * 1024 * 1024))
    top = memory.top_cgroups()
    names = [name for name, _ in top]
    expected = "user.slice/user-1000.slice/user@1000.service/app.slice/app-firefox-123.scope"
    assert expected in names
    assert names[0] == expected


def test_top_cgroups_missing_tree(fake_stack, tmp_path, monkeypatch):
    monkeypatch.setenv("KUTU_SYSFS", str(tmp_path / "nothing"))
    assert memory.top_cgroups() == []


def test_dashboard_frame_renders(fake_stack):
    frame = dash.build_frame()
    console = Console(record=True, width=110, force_terminal=False)
    console.print(frame)
    text = console.export_text()
    assert "kutu-doctor" in text
    assert "zswap" in text
    assert "top consumers" in text
    assert "user.slice" in text
    assert "firefox" in text


def _render(frame) -> str:
    console = Console(record=True, width=110, force_terminal=False)
    console.print(frame)
    return console.export_text()


def test_unreadable_values_render_as_unknown_not_off_or_none(fake_stack, monkeypatch, tmp_path):
    empty_sys = tmp_path / "empty-sys"
    empty_proc = tmp_path / "empty-proc"
    empty_sys.mkdir()
    empty_proc.mkdir()
    monkeypatch.setenv("KUTU_SYSFS", str(empty_sys))
    monkeypatch.setenv("KUTU_PROC", str(empty_proc))
    text = _render(dash.build_frame(services=False))
    assert "None" not in text
    mglru_line = next(line for line in text.splitlines() if "mglru" in line)
    assert "off" not in mglru_line
    assert "?" in mglru_line


def test_missing_pressure_and_available_do_not_print_none(fake_stack):
    (fake_stack["proc"] / "pressure/memory").write_text("some avg300=1.0 total=1\n")
    text = _render(dash.build_frame(services=False))
    assert "None" not in text


def test_status_table_marks_unreadable_mglru_unknown(fake_stack, monkeypatch, tmp_path):
    from kutu_doctor import render

    empty = tmp_path / "e"
    empty.mkdir()
    monkeypatch.setenv("KUTU_SYSFS", str(empty))
    stack = memory.gather(include_services=False)
    console = Console(record=True, width=110, force_terminal=False)
    console.print(render.status_table(stack, []))
    mglru_line = next(x for x in console.export_text().splitlines() if "mglru" in x)
    assert "off" not in mglru_line


def test_zswap_ratio_follows_the_system_page_size(fake_stack, monkeypatch):
    monkeypatch.setattr(memory, "PAGE_SIZE", 16384)
    stats = memory.zswap_stats(fake_stack["memtotal_kb"])
    assert 3.9 < stats.compressed_ratio < 4.1


def test_top_cgroups_reaches_user_slice_on_a_busy_system(fake_stack):
    services = fake_stack["sys"] / "fs/cgroup/system.slice"
    for i in range(700):
        unit = services / f"unit-{i:04d}.service"
        unit.mkdir()
        (unit / "memory.current").write_text("1048576")
    names = [name for name, _ in memory.top_cgroups(limit=3)]
    assert names[0] == "user.slice/session-1.scope"


def test_long_cgroup_names_keep_their_leaf():
    name = "user.slice/user-1000.slice/user@1000.service/app.slice/app-firefox-123.scope"
    short = dash._short_cgroup(name)
    assert short.endswith("app.slice/app-firefox-123.scope")
    assert len(short) <= 34
    assert dash._short_cgroup("system.slice") == "system.slice"
