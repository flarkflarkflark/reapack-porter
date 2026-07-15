from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

from reapack_porter.settings import (
    AppSettings,
    load_settings,
    remember_bundle_path,
    remember_ini_path,
    remember_output_dir,
    save_settings,
    settings_path_for,
)


def test_settings_path_windows() -> None:
    path = settings_path_for(platform="win32", home="C:/Users/Flark", env={"LOCALAPPDATA": "C:/Users/Flark/AppData/Local"})
    assert path == Path("C:/Users/Flark/AppData/Local/ReaPack Porter/settings.json")


def test_settings_path_linux() -> None:
    path = settings_path_for(platform="linux", home="/home/flark", env={})
    assert path == Path("/home/flark/.config/reapack-porter/settings.json")


def test_settings_path_linux_xdg() -> None:
    path = settings_path_for(platform="linux", home="/home/flark", env={"XDG_CONFIG_HOME": "/tmp/xdg"})
    assert path == Path("/tmp/xdg/reapack-porter/settings.json")


def test_settings_path_macos() -> None:
    path = settings_path_for(platform="darwin", home="/Users/flark", env={})
    assert path == Path("/Users/flark/Library/Application Support/ReaPack Porter/settings.json")


def test_corrupt_settings_json_does_not_crash(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    settings = load_settings(platform="linux", home=tmp_path, env={}, settings_path=path)
    assert settings == AppSettings()


def test_settings_atomic_write(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(AppSettings(source_ini="/tmp/a"), platform="linux", home=tmp_path, env={}, settings_path=path)
    assert path.is_file()
    assert not list(tmp_path.glob("settings.json.tmp.*"))


def test_settings_module_writes_nothing_on_import(tmp_path: Path, monkeypatch) -> None:
    sys.modules.pop("reapack_porter.settings", None)
    monkeypatch.chdir(tmp_path)
    importlib.import_module("reapack_porter.settings")
    assert list(tmp_path.iterdir()) == []


def test_custom_paths_are_remembered(tmp_path: Path) -> None:
    settings = AppSettings()
    settings = remember_ini_path(settings, "source_ini", tmp_path / "custom.ini")
    settings = remember_output_dir(settings, tmp_path / "out")
    settings = remember_bundle_path(settings, tmp_path / "bundle.zip")
    assert settings.source_ini == str(tmp_path / "custom.ini")
    assert settings.output_dir == str(tmp_path / "out")
    assert settings.bundle_path == str(tmp_path / "bundle.zip")
    assert settings.recent_ini_paths[0] == str(tmp_path / "custom.ini")


def test_unknown_fields_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"source_ini": "/tmp/x", "extra": 1}), encoding="utf-8")
    settings = load_settings(platform="linux", home=tmp_path, env={}, settings_path=path)
    assert settings.source_ini == "/tmp/x"
