from __future__ import annotations

import subprocess

import pytest

from kutu_doctor import system


def test_run_missing_binary_unchecked_does_not_raise():
    proc = system.run(["/nonexistent/binary"], check=False)
    assert proc.returncode == 127


def test_run_missing_binary_checked_raises_run_error():
    with pytest.raises(system.RunError):
        system.run(["/nonexistent/binary"])


def test_run_timeout_unchecked_does_not_raise():
    proc = system.run(["sleep", "5"], check=False, timeout=0.1)
    assert proc.returncode == 124


def test_run_timeout_checked_raises_run_error():
    with pytest.raises(system.RunError):
        system.run(["sleep", "5"], timeout=0.1)


def test_service_active_hung_systemctl_is_indeterminate(monkeypatch):
    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    monkeypatch.setattr(subprocess, "run", hang)
    assert system.service_active("systemd-oomd") is None


def test_require_root_names_the_real_command(monkeypatch, capsys):
    monkeypatch.delenv("KUTU_ROOT", raising=False)
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    with pytest.raises(SystemExit):
        system.require_root("mode set saver")
    assert "sudo kutu-doctor" in capsys.readouterr().err
