from __future__ import annotations

import json

from typer.testing import CliRunner

from kutu_doctor.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "kutu-doctor 0." in result.stdout


def test_status_human(fake_stack):
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "memory stack" in result.stdout
    assert "zswap" in result.stdout
    assert "firefox" in result.stdout


def test_status_json(fake_stack):
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mode"]["current"] == "balanced"
    assert payload["zswap"]["max_pool_percent"] == 35
    apps_by_name = {a["name"]: a for a in payload["apps"]}
    expected = fake_stack["memtotal_kb"] * 1024 * 50 // 100
    assert apps_by_name["firefox"]["effective_memory_high"] == expected
    assert apps_by_name["custom"]["memory_high_pct"] == 33


def test_check_pass(fake_stack):
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0
    assert "all checks passed" in result.stdout


def test_check_failure_exit_code(fake_stack):
    (fake_stack["sys"] / "module/zswap/parameters/max_pool_percent").write_text("20")
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1
    assert "failed" in result.stdout


def test_check_json(fake_stack):
    result = runner.invoke(app, ["check", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    names = {c["name"] for c in payload["checks"]}
    assert "zswap-pool-cap" in names
    assert payload["failed"] == 0


def test_mode_set(fake_stack):
    result = runner.invoke(app, ["mode", "set", "saver"])
    assert result.exit_code == 0, result.stdout
    assert "mode set" in result.stdout
    assert "MODE=saver" in (fake_stack["etc"] / "kutu/memory.conf").read_text()
    assert "set-property" in fake_stack["log"].read_text()


def test_mode_set_unknown(fake_stack):
    result = runner.invoke(app, ["mode", "set", "turbo"])
    assert result.exit_code == 2


def test_mode_apply(fake_stack):
    result = runner.invoke(app, ["mode", "apply"])
    assert result.exit_code == 0, result.stdout
    assert "applied" in result.stdout


def test_apps_list(fake_stack):
    result = runner.invoke(app, ["apps"])
    assert result.exit_code == 0
    assert "firefox" in result.stdout
    assert "custom" in result.stdout


def test_apps_run_dry(fake_stack, monkeypatch):
    monkeypatch.setenv("KUTU_DRY_RUN", "1")
    result = runner.invoke(app, ["apps", "run", "firefox", "/usr/bin/sleep", "10"])
    assert result.exit_code == 0, result.stdout
    assert "--unit=app-firefox-" in result.stdout
    assert "-p MemoryHigh=" in result.stdout


def test_apps_run_missing_profile(fake_stack):
    result = runner.invoke(app, ["apps", "run", "nope", "true"])
    assert result.exit_code == 2


def _all_output(result) -> str:
    import contextlib

    stderr = ""
    with contextlib.suppress(ValueError, AttributeError):
        stderr = result.stderr
    return result.output + stderr


def test_reset_missing_binary(fake_stack):
    result = runner.invoke(app, ["reset", "--yes"])
    assert result.exit_code == 1
    assert "kutu-reset not found" in _all_output(result)
