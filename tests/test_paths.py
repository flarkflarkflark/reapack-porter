from pathlib import Path

from reapack_porter.paths import default_reapack_ini_path


def test_linux_default_path() -> None:
    path = default_reapack_ini_path(platform="linux", home="/home/flark", env={})
    assert path == Path("/home/flark/.config/REAPER/reapack.ini")


def test_windows_default_path_uses_appdata() -> None:
    path = default_reapack_ini_path(
        platform="win32",
        home="C:/Users/Flark",
        env={"APPDATA": "C:/Users/Flark/AppData/Roaming"},
    )
    assert path == Path("C:/Users/Flark/AppData/Roaming/REAPER/reapack.ini")


def test_macos_default_path() -> None:
    path = default_reapack_ini_path(platform="darwin", home="/Users/flark", env={})
    assert path == Path("/Users/flark/Library/Application Support/REAPER/reapack.ini")


def test_windows_fallback_without_appdata() -> None:
    path = default_reapack_ini_path(platform="windows", home="C:/Users/Flark", env={})
    assert path == Path("C:/Users/Flark/AppData/Roaming/REAPER/reapack.ini")
