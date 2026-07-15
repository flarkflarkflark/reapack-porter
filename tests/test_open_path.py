from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from reapack_porter.paths import open_path


def test_open_path_windows_uses_argument_list(tmp_path: Path) -> None:
    called = {}
    folder = tmp_path / "folder"
    folder.mkdir()

    def runner(args):
        called["args"] = args
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    open_path(folder, platform="win32", runner=runner)
    assert called["args"] == ["explorer", str(folder)]


def test_open_path_macos_uses_argument_list(tmp_path: Path) -> None:
    called = {}
    folder = tmp_path / "folder"
    folder.mkdir()

    def runner(args):
        called["args"] = args
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    open_path(folder, platform="darwin", runner=runner)
    assert called["args"] == ["open", str(folder)]


def test_open_path_linux_uses_argument_list_and_zip_parent(tmp_path: Path) -> None:
    called = {}
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_text("zip", encoding="utf-8")

    def runner(args):
        called["args"] = args
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    opened = open_path(zip_path, platform="linux", runner=runner)
    assert opened == tmp_path
    assert called["args"] == ["xdg-open", str(tmp_path)]


def test_open_path_missing_command_raises(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()

    def runner(args):
        raise FileNotFoundError("missing")

    with pytest.raises(RuntimeError, match="required command not found"):
        open_path(folder, platform="linux", runner=runner)


def test_open_path_non_zero_raises(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()

    def runner(args):
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="bad")

    with pytest.raises(RuntimeError, match="command failed"):
        open_path(folder, platform="linux", runner=runner)
