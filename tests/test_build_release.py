from __future__ import annotations

from pathlib import Path
import subprocess

import pytest
import tomllib

from tools import build_release


def test_repo_root_is_independent_of_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert build_release.repo_root() == Path(__file__).resolve().parents[1]


def test_parse_args_accepts_valid_targets() -> None:
    for target in ("gui", "cli", "all"):
        args = build_release.parse_args(["--target", target])
        assert args.target == target


def test_parse_args_rejects_invalid_target() -> None:
    with pytest.raises(SystemExit) as exc:
        build_release.parse_args(["--target", "installer"])
    assert exc.value.code == 2


def test_platform_normalization() -> None:
    assert build_release.normalize_platform("linux") == "linux"
    assert build_release.normalize_platform("win32") == "windows"
    assert build_release.normalize_platform("windows") == "windows"
    assert build_release.normalize_platform("darwin") == "macos"


def test_architecture_normalization() -> None:
    assert build_release.normalize_arch("x86_64") == "x86_64"
    assert build_release.normalize_arch("AMD64") == "x86_64"
    assert build_release.normalize_arch("arm64") == "arm64"
    assert build_release.normalize_arch("aarch64") == "arm64"


def test_specs_are_selected_per_target() -> None:
    root = build_release.repo_root()
    assert build_release.spec_for_target("gui", root) == root / "tools" / "pyinstaller" / "reapack_porter_gui.spec"
    assert build_release.spec_for_target("cli", root) == root / "tools" / "pyinstaller" / "reapack_porter_cli.spec"


def test_target_expansion() -> None:
    assert build_release.expand_targets("gui") == ("gui",)
    assert build_release.expand_targets("cli") == ("cli",)
    assert build_release.expand_targets("all") == ("gui", "cli")


def test_gui_build_checks_tkinter_before_pyinstaller(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_check_tkinter() -> None:
        calls.append("tk")

    def fake_run_pyinstaller(*args, **kwargs) -> None:
        calls.append("pyinstaller")

    monkeypatch.setattr(build_release, "check_tkinter", fake_check_tkinter)
    monkeypatch.setattr(build_release, "run_pyinstaller", fake_run_pyinstaller)

    build_release.build_target(
        "gui",
        repo_root=build_release.repo_root(),
        dist_dir=tmp_path / "dist",
        work_dir=tmp_path / "work",
        clean=False,
        debug=False,
    )

    assert calls == ["tk", "pyinstaller"]


def test_cli_build_does_not_check_tkinter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail_check_tkinter() -> None:
        raise AssertionError("CLI build must not check tkinter")

    monkeypatch.setattr(build_release, "check_tkinter", fail_check_tkinter)
    monkeypatch.setattr(build_release, "run_pyinstaller", lambda *args, **kwargs: None)

    build_release.build_target(
        "cli",
        repo_root=build_release.repo_root(),
        dist_dir=tmp_path / "dist",
        work_dir=tmp_path / "work",
        clean=False,
        debug=False,
    )


def test_pyinstaller_is_invoked_without_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(build_release.subprocess, "run", fake_run)

    build_release.run_pyinstaller(
        build_release.repo_root() / "tools" / "pyinstaller" / "reapack_porter_cli.spec",
        repo_root=build_release.repo_root(),
        dist_dir=tmp_path / "dist",
        work_dir=tmp_path / "work",
        log_level="INFO",
    )

    assert isinstance(captured["args"], list)
    assert captured["args"][:3] == [build_release.sys.executable, "-m", "PyInstaller"]
    assert captured["kwargs"]["shell"] is False


def test_missing_pyinstaller_reports_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="No module named PyInstaller")

    monkeypatch.setattr(build_release.subprocess, "run", fake_run)

    with pytest.raises(build_release.BuildError, match="PyInstaller is not installed"):
        build_release.run_pyinstaller(
            build_release.repo_root() / "tools" / "pyinstaller" / "reapack_porter_cli.spec",
            repo_root=build_release.repo_root(),
            dist_dir=build_release.repo_root() / "dist",
            work_dir=build_release.repo_root() / ".pyinstaller-work",
            log_level="INFO",
        )


def test_pyinstaller_build_failure_is_not_reported_as_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=9, stdout="", stderr="spec failed")

    monkeypatch.setattr(build_release.subprocess, "run", fake_run)

    with pytest.raises(build_release.BuildError, match="PyInstaller failed for reapack_porter_cli.spec"):
        build_release.run_pyinstaller(
            build_release.repo_root() / "tools" / "pyinstaller" / "reapack_porter_cli.spec",
            repo_root=build_release.repo_root(),
            dist_dir=tmp_path / "dist",
            work_dir=tmp_path / ".pyinstaller-work",
            log_level="INFO",
        )


def test_clean_removes_only_generated_directories(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    work = tmp_path / ".pyinstaller-work"
    source = tmp_path / "src"
    for path in (dist, work, source):
        path.mkdir()
        (path / "marker.txt").write_text("x", encoding="utf-8")

    build_release.clean_outputs(dist, work)

    assert not dist.exists()
    assert not work.exists()
    assert source.is_dir()
    assert (source / "marker.txt").is_file()


def test_clean_rejects_source_like_paths(tmp_path: Path) -> None:
    with pytest.raises(build_release.BuildError):
        build_release.clean_outputs(tmp_path / "src", tmp_path / ".pyinstaller-work")


def test_pyproject_build_extra_matches_validated_pyinstaller_floor() -> None:
    data = tomllib.loads((build_release.repo_root() / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["optional-dependencies"]["build"] == ["PyInstaller>=6.19,<7"]
