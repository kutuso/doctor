from __future__ import annotations

from rich.console import Console

from kutu_doctor import dash, memory


def test_top_cgroups_sorted(fake_stack):
    top = memory.top_cgroups()
    names = [name for name, _ in top]
    assert names[0] == "user.slice"
    assert "user.slice/session-1.scope" in names
    assert "system.slice" in names
    values = [value for _, value in top]
    assert values == sorted(values, reverse=True)


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
