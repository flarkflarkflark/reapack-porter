from __future__ import annotations

from pathlib import Path

from reapack_porter.paths import (
    STATUS_DETECTED,
    STATUS_EXPECTED,
    STATUS_MANUAL,
    STATUS_REMEMBERED,
    default_reapack_ini_path,
    resolve_reapack_ini_path,
)


def test_windows_standard_path() -> None:
    path = default_reapack_ini_path(platform="win32", home="C:/Users/Flark", env={"APPDATA": "C:/Users/Flark/AppData/Roaming"})
    assert path == Path("C:/Users/Flark/AppData/Roaming/REAPER/reapack.ini")


def test_linux_standard_path() -> None:
    path = default_reapack_ini_path(platform="linux", home="/home/flark", env={})
    assert path == Path("/home/flark/.config/REAPER/reapack.ini")


def test_linux_standard_path_xdg() -> None:
    path = default_reapack_ini_path(platform="linux", home="/home/flark", env={"XDG_CONFIG_HOME": "/tmp/xdg"})
    assert path == Path("/tmp/xdg/REAPER/reapack.ini")


def test_macos_standard_path() -> None:
    path = default_reapack_ini_path(platform="darwin", home="/Users/flark", env={})
    assert path == Path("/Users/flark/Library/Application Support/REAPER/reapack.ini")


def test_existing_remembered_path_wins(tmp_path: Path) -> None:
    remembered = tmp_path / "remembered.ini"
    remembered.write_text("x", encoding="utf-8")
    resolved = resolve_reapack_ini_path(platform="linux", home=tmp_path, env={}, remembered_path=remembered)
    assert resolved.path == remembered
    assert resolved.status == STATUS_REMEMBERED


def test_missing_remembered_falls_back_to_existing_default(tmp_path: Path) -> None:
    default_path = tmp_path / ".config" / "REAPER" / "reapack.ini"
    default_path.parent.mkdir(parents=True)
    default_path.write_text("x", encoding="utf-8")
    resolved = resolve_reapack_ini_path(
        platform="linux",
        home=tmp_path,
        env={},
        remembered_path=tmp_path / "missing.ini",
    )
    assert resolved.path == default_path
    assert resolved.status == STATUS_DETECTED


def test_no_existing_file_returns_expected_default(tmp_path: Path) -> None:
    resolved = resolve_reapack_ini_path(platform="linux", home=tmp_path, env={})
    assert resolved.exists is False
    assert resolved.status == STATUS_EXPECTED


def test_explicit_path_is_manual(tmp_path: Path) -> None:
    path = tmp_path / "manual.ini"
    resolved = resolve_reapack_ini_path(platform="linux", home=tmp_path, env={}, explicit_path=path)
    assert resolved.path == path
    assert resolved.status == STATUS_MANUAL


def test_portable_current_workdir_candidate(tmp_path: Path) -> None:
    (tmp_path / "reaper.ini").write_text("x", encoding="utf-8")
    portable = tmp_path / "reapack.ini"
    portable.write_text("x", encoding="utf-8")
    resolved = resolve_reapack_ini_path(platform="linux", home=tmp_path / "home", env={}, cwd=tmp_path)
    assert resolved.path == portable
    assert resolved.status == STATUS_DETECTED
