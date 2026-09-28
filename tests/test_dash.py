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
