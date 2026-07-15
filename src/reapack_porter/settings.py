from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


@dataclass(frozen=True)
class AppSettings:
    source_ini: str | None = None
    target_ini: str | None = None
    output_dir: str | None = None
    bundle_path: str | None = None
    recent_ini_paths: tuple[str, ...] = ()


def settings_path_for(
    *,
    platform: str,
    home: str | Path,
    env: Mapping[str, str] | None = None,
) -> Path:
    env_map = dict(env or {})
    home_path = Path(home)
    normalized = platform.lower()

    if normalized.startswith("win"):
        local = env_map.get("LOCALAPPDATA")
        base = Path(local) if local else home_path / "AppData" / "Local"
        return base / "ReaPack Porter" / "settings.json"
    if normalized == "darwin":
        return home_path / "Library" / "Application Support" / "ReaPack Porter" / "settings.json"
    xdg = env_map.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else home_path / ".config"
    return base / "reapack-porter" / "settings.json"


def load_settings(
    *,
    platform: str,
    home: str | Path,
    env: Mapping[str, str] | None = None,
    settings_path: str | Path | None = None,
) -> AppSettings:
    path = Path(settings_path) if settings_path is not None else settings_path_for(platform=platform, home=home, env=env)
    if not path.is_file():
        return AppSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return AppSettings()
    if not isinstance(data, dict):
        return AppSettings()
    recent = data.get("recent_ini_paths")
    recent_paths: tuple[str, ...]
    if isinstance(recent, list):
        recent_paths = tuple(str(item) for item in recent if isinstance(item, str))
    else:
        recent_paths = ()
    return AppSettings(
        source_ini=data.get("source_ini") if isinstance(data.get("source_ini"), str) else None,
        target_ini=data.get("target_ini") if isinstance(data.get("target_ini"), str) else None,
        output_dir=data.get("output_dir") if isinstance(data.get("output_dir"), str) else None,
        bundle_path=data.get("bundle_path") if isinstance(data.get("bundle_path"), str) else None,
        recent_ini_paths=recent_paths,
    )


def save_settings(
    settings: AppSettings,
    *,
    platform: str,
    home: str | Path,
    env: Mapping[str, str] | None = None,
    settings_path: str | Path | None = None,
) -> Path:
    path = Path(settings_path) if settings_path is not None else settings_path_for(platform=platform, home=home, env=env)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "source_ini": settings.source_ini,
        "target_ini": settings.target_ini,
        "output_dir": settings.output_dir,
        "bundle_path": settings.bundle_path,
        "recent_ini_paths": list(settings.recent_ini_paths),
    }
    fd, temp_name = tempfile.mkstemp(prefix=f"{path.name}.tmp.", dir=path.parent, text=True)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    return path


def remember_ini_path(settings: AppSettings, key: str, path: str | Path) -> AppSettings:
    path_str = str(path)
    recent = (path_str,) + tuple(item for item in settings.recent_ini_paths if item != path_str)
    recent = recent[:8]
    values = {
        "source_ini": settings.source_ini,
        "target_ini": settings.target_ini,
        "output_dir": settings.output_dir,
        "bundle_path": settings.bundle_path,
        "recent_ini_paths": recent,
    }
    values[key] = path_str
    return AppSettings(**values)


def remember_output_dir(settings: AppSettings, output_dir: str | Path) -> AppSettings:
    return AppSettings(
        source_ini=settings.source_ini,
        target_ini=settings.target_ini,
        output_dir=str(output_dir),
        bundle_path=settings.bundle_path,
        recent_ini_paths=settings.recent_ini_paths,
    )


def remember_bundle_path(settings: AppSettings, bundle_path: str | Path) -> AppSettings:
    return AppSettings(
        source_ini=settings.source_ini,
        target_ini=settings.target_ini,
        output_dir=settings.output_dir,
        bundle_path=str(bundle_path),
        recent_ini_paths=settings.recent_ini_paths,
    )
