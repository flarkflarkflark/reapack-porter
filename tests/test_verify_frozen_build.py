from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from tools import verify_frozen_build


def test_architecture_normalization() -> None:
    assert verify_frozen_build.normalize_arch("AMD64") == "x86_64"
    assert verify_frozen_build.normalize_arch("x86_64") == "x86_64"
    assert verify_frozen_build.normalize_arch("aarch64") == "arm64"
    assert verify_frozen_build.normalize_arch("arm64") == "arm64"


def test_expected_outputs_per_platform(tmp_path: Path) -> None:
    assert verify_frozen_build.expected_outputs("linux", tmp_path).gui == tmp_path / "ReaPack-Porter" / "ReaPack-Porter"
    assert verify_frozen_build.expected_outputs("windows", tmp_path).cli == tmp_path / "reapack-porter-cli.exe"
    app = tmp_path / "ReaPack Porter.app" / "Contents"
    app.mkdir(parents=True)
    (app / "Info.plist").write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        b'"http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict>'
        b"<key>CFBundleExecutable</key><string>CustomExe</string></dict></plist>"
    )
    assert verify_frozen_build.expected_outputs("macos", tmp_path).gui == app / "MacOS" / "CustomExe"


def test_architecture_mismatch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify_frozen_build.platform_module, "machine", lambda: "aarch64")
    with pytest.raises(verify_frozen_build.VerificationError, match="Architecture mismatch"):
        verify_frozen_build.check_architecture("x86_64")


def test_run_command_removes_pythonpath_and_uses_arg_list(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setenv("PYTHONPATH", "leak")
    monkeypatch.setattr(verify_frozen_build.subprocess, "run", fake_run)
    verify_frozen_build.run_command(["tool", "--help"])
    assert captured["args"] == ["tool", "--help"]
    assert captured["kwargs"]["shell"] is False
    assert "PYTHONPATH" not in captured["kwargs"]["env"]


def test_clean_env_uses_temporary_home_and_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYTHONPATH", "leak")
    env = verify_frozen_build.clean_env(tmp_path)
    assert env["HOME"] == str(tmp_path / "home")
    assert env["USERPROFILE"] == str(tmp_path / "profile")
    assert env["XDG_CONFIG_HOME"] == str(tmp_path / "xdg")
    assert "PYTHONPATH" not in env
    assert (tmp_path / "home").is_dir()
    assert (tmp_path / "profile").is_dir()
    assert (tmp_path / "xdg").is_dir()


def test_cli_smoke_runs_all_help_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(verify_frozen_build, "require_success", lambda args, **kwargs: calls.append(args))
    verify_frozen_build.run_cli_smoke(tmp_path / "cli", env={})
    assert calls == [
        [str(tmp_path / "cli"), "--help"],
        [str(tmp_path / "cli"), "export", "--help"],
        [str(tmp_path / "cli"), "import", "--help"],
    ]


def test_frozen_cli_e2e_runs_export_zip_and_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_require_success(args, **kwargs):
        calls.append(args)
        if "--zip" in args:
            out_dir = Path(args[args.index("--out") + 1])
            out_dir.mkdir(parents=True)
            (out_dir / "bundle.zip").write_text("zip", encoding="utf-8")

    monkeypatch.setattr(verify_frozen_build, "require_success", fake_require_success)
    verify_frozen_build.run_frozen_cli_e2e(tmp_path / "cli", env={})
    assert calls[0][1:4] == ["export", "--source", calls[0][3]]
    assert calls[1][1] == "export"
    assert "--zip" in calls[1]
    assert calls[2][1] == "import"
    assert "--dry-run" in calls[2]


def test_linux_gui_timeout_is_accepted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verify_frozen_build.shutil, "which", lambda name: "/usr/bin/xvfb-run")
    monkeypatch.setattr(
        verify_frozen_build,
        "run_command",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=124, stdout="", stderr=""),
    )
    verify_frozen_build.run_gui_smoke("linux", tmp_path / "gui", env={})


def test_linux_gui_crash_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verify_frozen_build.shutil, "which", lambda name: "/usr/bin/xvfb-run")
    monkeypatch.setattr(
        verify_frozen_build,
        "run_command",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=2, stdout="", stderr="boom"),
    )
    with pytest.raises(verify_frozen_build.VerificationError, match="GUI smoke failed"):
        verify_frozen_build.run_gui_smoke("linux", tmp_path / "gui", env={})


def test_windows_or_macos_gui_launch_uses_popen_without_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        stdout = None
        stderr = None
        terminated = False

        def wait(self, timeout):
            if self.terminated:
                return 0
            raise subprocess.TimeoutExpired(cmd="gui", timeout=timeout)

        def terminate(self):
            captured["terminated"] = True
            self.terminated = True

        def kill(self):
            captured["killed"] = True

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(verify_frozen_build.subprocess, "Popen", fake_popen)
    verify_frozen_build.run_gui_smoke("windows", tmp_path / "gui.exe", env={})
    assert captured["args"] == [str(tmp_path / "gui.exe")]
    assert captured["kwargs"]["shell"] is False
    assert captured["terminated"] is True


def test_windows_or_macos_gui_kills_after_terminate_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {"waits": 0}

    class FakeProcess:
        stdout = None
        stderr = None

        def wait(self, timeout):
            captured["waits"] = int(captured["waits"]) + 1
            if captured["waits"] >= 3:
                return 0
            raise subprocess.TimeoutExpired(cmd="gui", timeout=timeout)

        def terminate(self):
            captured["terminated_before_kill"] = "killed" not in captured

        def kill(self):
            captured["killed"] = True

    monkeypatch.setattr(verify_frozen_build.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    verify_frozen_build.run_gui_smoke("macos", tmp_path / "gui", env={})
    assert captured["terminated_before_kill"] is True
    assert captured["killed"] is True


def test_verify_frozen_build_runs_expected_phases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gui = tmp_path / "ReaPack-Porter" / "ReaPack-Porter"
    gui.parent.mkdir()
    cli = tmp_path / "reapack-porter-cli"
    gui.write_text("", encoding="utf-8")
    cli.write_text("", encoding="utf-8")
    gui.chmod(0o755)
    cli.chmod(0o755)
    calls: list[str] = []
    monkeypatch.setattr(verify_frozen_build, "check_architecture", lambda arch: calls.append(f"arch:{arch}"))
    monkeypatch.setattr(verify_frozen_build, "run_cli_smoke", lambda cli, env: calls.append("cli"))
    monkeypatch.setattr(verify_frozen_build, "run_frozen_cli_e2e", lambda cli, env: calls.append("cli-e2e"))
    monkeypatch.setattr(verify_frozen_build, "run_operations_e2e", lambda platform: calls.append("e2e"))
    monkeypatch.setattr(verify_frozen_build, "run_gui_smoke", lambda platform, gui, env: calls.append("gui"))
    verify_frozen_build.verify_frozen_build(platform="linux", arch="x86_64", dist_dir=tmp_path)
    assert calls == ["arch:x86_64", "cli", "cli-e2e", "e2e", "gui"]
