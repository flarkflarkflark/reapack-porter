from __future__ import annotations

from pathlib import Path
from typing import Mapping


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
        appdata = env_map.get("APPDATA")
        if appdata:
            return Path(appdata) / "REAPER" / "reapack.ini"
        return home_path / "AppData" / "Roaming" / "REAPER" / "reapack.ini"
    if normalized == "darwin":
        return home_path / "Library" / "Application Support" / "REAPER" / "reapack.ini"
    return home_path / ".config" / "REAPER" / "reapack.ini"


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
