from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Mapping


@dataclass(frozen=True)
class ResolvedIniPath:
    path: Path
    exists: bool
    status: str


STATUS_DETECTED = "detected"
STATUS_REMEMBERED = "remembered"
STATUS_EXPECTED = "expected_missing"
STATUS_MANUAL = "manual"


def _config_home(*, platform: str, home: Path, env: Mapping[str, str]) -> Path:
    normalized = platform.lower()
    if normalized.startswith("win"):
        appdata = env.get("APPDATA")
        if appdata:
            return Path(appdata)
        return home / "AppData" / "Roaming"
    if normalized == "darwin":
        return home / "Library" / "Application Support"
    xdg = env.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return home / ".config"


def default_reapack_ini_path(
    *,
    platform: str,
    home: str | Path,
    env: Mapping[str, str] | None = None,
) -> Path:
    env_map = dict(env or {})
    home_path = Path(home)
    normalized = platform.lower()

    if normalized.startswith("win"):
        return _config_home(platform=platform, home=home_path, env=env_map) / "REAPER" / "reapack.ini"
    if normalized == "darwin":
        return home_path / "Library" / "Application Support" / "REAPER" / "reapack.ini"
    return _config_home(platform=platform, home=home_path, env=env_map) / "REAPER" / "reapack.ini"


def default_documents_dir(
    *,
    platform: str,
    home: str | Path,
    cwd: str | Path,
) -> Path:
    del platform
    home_path = Path(home)
    documents = home_path / "Documents"
    if documents.exists():
        return documents
    return Path(cwd)


def resolve_reapack_ini_path(
    *,
    platform: str,
    home: str | Path,
    env: Mapping[str, str] | None = None,
    explicit_path: str | Path | None = None,
    remembered_path: str | Path | None = None,
    cwd: str | Path | None = None,
    reaper_executable: str | Path | None = None,
) -> ResolvedIniPath:
    env_map = dict(env or {})
    home_path = Path(home)
    default_path = default_reapack_ini_path(platform=platform, home=home_path, env=env_map)

    if explicit_path is not None:
        explicit = Path(explicit_path)
        return ResolvedIniPath(path=explicit, exists=explicit.is_file(), status=STATUS_MANUAL)

    if remembered_path is not None:
        remembered = Path(remembered_path)
        if remembered.is_file():
            return ResolvedIniPath(path=remembered, exists=True, status=STATUS_REMEMBERED)

    if default_path.is_file():
        return ResolvedIniPath(path=default_path, exists=True, status=STATUS_DETECTED)

    if cwd is not None:
        cwd_path = Path(cwd)
        portable_reaper = cwd_path / "reaper.ini"
        portable_reapack = cwd_path / "reapack.ini"
        if portable_reaper.is_file() and portable_reapack.is_file():
            return ResolvedIniPath(path=portable_reapack, exists=True, status=STATUS_DETECTED)

    if reaper_executable is not None:
        candidate = Path(reaper_executable).parent / "reapack.ini"
        if candidate.is_file():
            return ResolvedIniPath(path=candidate, exists=True, status=STATUS_DETECTED)

    return ResolvedIniPath(path=default_path, exists=False, status=STATUS_EXPECTED)


def open_path(
    path: str | Path,
    *,
    platform: str,
    runner=None,
) -> Path:
    target = Path(path)
    open_target = target.parent if target.is_file() else target
    if platform.lower().startswith("win"):
        command = ["explorer", str(open_target)]
    elif platform.lower() == "darwin":
        command = ["open", str(open_target)]
    else:
        command = ["xdg-open", str(open_target)]

    runner = runner or (lambda args: subprocess.run(args, check=False, capture_output=True, text=True))
    try:
        result = runner(command)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Could not open path: required command not found for {open_target}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"Could not open path: command failed for {open_target}")
    return open_target
