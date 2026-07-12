from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable


class IniFormatError(ValueError):
    pass


class BackupError(RuntimeError):
    pass


class ImportVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Remote:
    name: str
    url: str
    enabled: str
    autosync: str


@dataclass(frozen=True)
class ParsedRemotes:
    remotes: list[Remote]
    declared_size: int | None
    section_present: bool


def normalize_url(url: str) -> str:
    return url.strip().lower().rstrip("/")


def _trim(value: str) -> str:
    return value.strip()


def _split_lines(text: str) -> list[str]:
    return text.splitlines()


def detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def parse_remotes(ini_text: str) -> ParsedRemotes:
    in_remotes = False
    section_present = False
    remotes: list[Remote] = []
    declared_size: int | None = None

    for raw_line in _split_lines(ini_text):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1]
            in_remotes = section_name == "remotes"
            section_present = section_present or in_remotes
            continue
        if not in_remotes:
            continue
        if line.startswith("remote"):
            key, sep, value = raw_line.partition("=")
            if not sep or not key.startswith("remote"):
                continue
            parts = value.split("|")
            if len(parts) != 4:
                raise IniFormatError(f"Invalid remote entry: {raw_line}")
            remotes.append(
                Remote(
                    name=_trim(parts[0]),
                    url=_trim(parts[1]),
                    enabled=_trim(parts[2]),
                    autosync=_trim(parts[3]),
                )
            )
            continue
        if line.startswith("size="):
            _, _, value = line.partition("=")
            try:
                declared_size = int(value.strip())
            except ValueError as exc:
                raise IniFormatError(f"Invalid remotes size value: {raw_line}") from exc

    return ParsedRemotes(
        remotes=remotes,
        declared_size=declared_size,
        section_present=section_present,
    )


def merge_remotes(existing_remotes: list[Remote], imported_remotes: list[Remote]) -> tuple[list[Remote], int, int]:
    seen = {normalize_url(remote.url) for remote in existing_remotes if normalize_url(remote.url)}
    merged = list(existing_remotes)
    added = 0
    skipped = 0

    for remote in imported_remotes:
        key = normalize_url(remote.url)
        if not key or key in seen:
            skipped += 1
            continue
        merged.append(remote)
        seen.add(key)
        added += 1

    return merged, added, skipped


def render_remotes_section(remotes: list[Remote], newline: str = "\n") -> str:
    lines = ["[remotes]"]
    for index, remote in enumerate(remotes):
        lines.append(
            f"remote{index}={remote.name}|{remote.url}|{remote.enabled}|{remote.autosync}"
        )
    lines.append(f"size={len(remotes)}")
    return newline.join(lines) + newline


def remove_remotes_section(ini_text: str) -> str:
    newline = detect_newline(ini_text)
    lines = _split_lines(ini_text)
    kept: list[str] = []
    in_remotes = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1]
            if section_name == "remotes":
                in_remotes = True
                continue
            if in_remotes:
                in_remotes = False
            kept.append(line)
            continue
        if not in_remotes:
            kept.append(line)

    text = newline.join(kept).rstrip("\r\n")
    return f"{text}{newline}" if text else ""


def replace_remotes_section(ini_text: str, remotes: list[Remote]) -> str:
    newline = detect_newline(ini_text)
    stripped = remove_remotes_section(ini_text).rstrip("\r\n")
    remotes_text = render_remotes_section(remotes, newline=newline).rstrip("\r\n")
    if stripped:
        return f"{stripped}{newline}{newline}{remotes_text}{newline}"
    return f"{remotes_text}{newline}"


def sorted_bundle_remotes(remotes: list[Remote]) -> list[Remote]:
    return sorted(
        remotes,
        key=lambda remote: (
            f"{remote.name}\t{remote.url}\t{remote.enabled}\t{remote.autosync}".lower()
        ),
    )


def backup_path_for(
    target_path: Path,
    *,
    now: datetime | None = None,
    exists: Callable[[Path], bool] | None = None,
) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    candidate = target_path.with_name(f"{target_path.name}.bak.{timestamp}")
    exists_fn = exists or Path.exists
    if not exists_fn(candidate):
        return candidate
    for index in range(1, 1000):
        indexed = target_path.with_name(f"{target_path.name}.bak.{timestamp}-{index}")
        if not exists_fn(indexed):
            return indexed
    raise BackupError(f"Could not create a unique backup path for {target_path}")


def import_remotes(
    target_ini_path: str | Path,
    imported_remotes: list[Remote],
    *,
    now: datetime | None = None,
) -> tuple[Path, int, int, int]:
    target_path = Path(target_ini_path)
    if not target_path.exists():
        raise FileNotFoundError(f"Target reapack.ini not found: {target_path}")

    with target_path.open("r", encoding="utf-8", newline="") as handle:
        original_text = handle.read()
    existing = parse_remotes(original_text)
    merged, added, skipped = merge_remotes(existing.remotes, imported_remotes)
    updated_text = replace_remotes_section(original_text, merged)

    backup_path = backup_path_for(target_path, now=now)
    try:
        shutil.copyfile(target_path, backup_path)
    except OSError as exc:
        raise BackupError(f"Failed to create backup at {backup_path}: {exc}") from exc

    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f"{target_path.name}.tmp.",
        dir=target_path.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated_text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target_path)

        with target_path.open("r", encoding="utf-8", newline="") as handle:
            written = handle.read()
        written_remotes = parse_remotes(written).remotes
        seen_after = {normalize_url(remote.url) for remote in written_remotes}
        missing = [
            remote.url
            for remote in imported_remotes
            if normalize_url(remote.url) and normalize_url(remote.url) not in seen_after
        ]
        if missing:
            raise ImportVerificationError(
                "Import verification failed; missing repositories after write: "
                + ", ".join(missing)
            )
        return backup_path, added, skipped, len(merged)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
