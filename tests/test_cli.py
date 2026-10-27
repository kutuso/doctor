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
    assert payload["indeterminate"] == 0


def test_check_indeterminate_exit_code(fake_stack, monkeypatch):
    monkeypatch.setenv("KUTU_SYSTEMCTL", "/nonexistent/systemctl")
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 2
    assert "could not be determined" in result.stdout


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


def test_apps_run_refuses_invalid_profile(fake_stack):
    (fake_stack["etc"] / "kutu/apps.d/bad.conf").write_text("KUTU_MEMORY_HIGH_PCT=500\n")
    result = runner.invoke(app, ["apps", "run", "bad", "true"])
    assert result.exit_code == 2
    assert "invalid" in _all_output(result)


def _all_output(result) -> str:
    import contextlib

    stderr = ""
    with contextlib.suppress(ValueError, AttributeError):
        stderr = result.stderr
    return result.output + stderr


def test_reset_missing_binary(fake_stack):
    result = runner.invoke(app, ["reset", "--yes"])
    assert result.exit_code == 2
    assert "KUTU_ROOT" in _all_output(result)


def test_reset_refused_on_target_root(fake_stack, monkeypatch):
    monkeypatch.delenv("KUTU_SANDBOX")
    result = runner.invoke(app, ["reset", "--yes"])
    assert result.exit_code == 2
    assert "refuses" in _all_output(result)


def test_mode_set_refused_on_target_root(fake_stack, monkeypatch):
    monkeypatch.delenv("KUTU_SANDBOX")
    result = runner.invoke(app, ["mode", "set", "saver"])
    assert result.exit_code == 2
    assert "refuses" in _all_output(result)
    assert "MODE=balanced" in (fake_stack["etc"] / "kutu/memory.conf").read_text()


def test_mode_set_refused_with_fake_kernel_paths_outside_sandbox(tmp_path, monkeypatch):
    for var in ("KUTU_ROOT", "KUTU_SANDBOX", "KUTU_SYSTEMCTL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KUTU_PROC", str(tmp_path))
    result = runner.invoke(app, ["mode", "set", "saver"])
    assert result.exit_code == 2
    assert "refuses" in _all_output(result)


def test_sandbox_rooted_at_slash_is_not_a_sandbox(monkeypatch):
    from kutu_doctor import paths

    monkeypatch.setenv("KUTU_ROOT", "/")
    monkeypatch.setenv("KUTU_SANDBOX", "1")
    assert paths.is_sandboxed() is False


def test_apps_run_passes_dashed_arguments_through(fake_stack, monkeypatch):
    monkeypatch.setenv("KUTU_DRY_RUN", "1")
    result = runner.invoke(app, ["apps", "run", "firefox", "firefox", "--new-window", "-P", "x"])
    assert result.exit_code == 0, _all_output(result)
    assert result.stdout.rstrip().endswith("-- firefox --new-window -P x")


def test_apps_run_missing_launcher_is_a_clean_error(fake_stack, monkeypatch):
    monkeypatch.setenv("KUTU_SYSTEMD_RUN", "/nonexistent/systemd-run")
    result = runner.invoke(app, ["apps", "run", "firefox", "true"])
    assert result.exit_code == 127
    assert "systemd-run" in _all_output(result)
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_check_hint_shows_the_check_name(fake_stack):
    (fake_stack["sys"] / "module/zswap/parameters/max_pool_percent").write_text("20")
    result = runner.invoke(app, ["check"])
    assert "hint [zswap-pool-cap]:" in _all_output(result)


def test_json_output_is_plain_even_with_forced_color(fake_stack, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    for args in (["status", "--json"], ["check", "--json"]):
        result = runner.invoke(app, args)
        assert "\x1b" not in result.stdout
        json.loads(result.stdout)


def test_dash_without_a_terminal_prints_one_frame_and_exits(fake_stack, monkeypatch):
    def forbidden(_seconds):
        raise RuntimeError("dashboard looped on a non-terminal")

    monkeypatch.setattr("time.sleep", forbidden)
    result = runner.invoke(app, ["dash"])
    assert result.exit_code == 0, result.output
    assert "top consumers" in result.stdout


def test_profile_names_with_markup_characters_do_not_crash(fake_stack):
    (fake_stack["etc"] / "kutu/apps.d/x[bold]y.conf").write_text("KUTU_MEMORY_HIGH_PCT=10\n")
    for args in (["apps"], ["status"], ["dash"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, (args, result.output)
        assert "x[bold]y" in result.stdout
