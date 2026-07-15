from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys
from typing import Callable

from .bundles import BundleError, create_bundle_zip, export_bundle, load_bundle_remotes
from .core import (
    BackupError,
    ImportVerificationError,
    ParsedRemotes,
    Remote,
    import_remotes,
    merge_remotes,
    parse_remotes,
)
from .paths import default_documents_dir, default_reapack_ini_path
from .processes import ProcessDetectionError, is_reaper_running


class ReaPackPorterError(RuntimeError):
    pass


class InvalidInputError(ReaPackPorterError):
    pass


class ReaperRunningError(ReaPackPorterError):
    pass


class ReaperDetectionError(ReaPackPorterError):
    pass


class ExportOperationError(ReaPackPorterError):
    pass


class ImportOperationError(ReaPackPorterError):
    pass


@dataclass(frozen=True)
class ExportResult:
    repository_count: int
    bundle_path: Path
    zip_path: Path | None


@dataclass(frozen=True)
class ImportPlan:
    imported_count: int
    added_count: int
    skipped_count: int
    total_count: int
    repositories: tuple[Remote, ...]


@dataclass(frozen=True)
class ImportResult:
    target_path: Path
    backup_path: Path
    added_count: int
    skipped_count: int
    total_count: int


@dataclass(frozen=True)
class OperationDeps:
    parse_remotes: Callable[[str], ParsedRemotes]
    merge_remotes: Callable[[list[Remote], list[Remote]], tuple[list[Remote], int, int]]
    export_bundle: Callable[[str | Path, list[Remote]], Path] | Callable[..., Path]
    create_bundle_zip: Callable[[str | Path], Path] | Callable[..., Path]
    load_bundle_remotes: Callable[[str | Path], list[Remote]]
    import_remotes: Callable[[str | Path, list[Remote]], tuple[Path, int, int, int]] | Callable[..., tuple[Path, int, int, int]]
    default_reapack_ini_path: Callable[..., Path]
    default_documents_dir: Callable[..., Path]
    is_reaper_running: Callable[..., bool]
    now: Callable[[], datetime]


DEFAULT_DEPS = OperationDeps(
    parse_remotes=parse_remotes,
    merge_remotes=merge_remotes,
    export_bundle=export_bundle,
    create_bundle_zip=create_bundle_zip,
    load_bundle_remotes=load_bundle_remotes,
    import_remotes=import_remotes,
    default_reapack_ini_path=default_reapack_ini_path,
    default_documents_dir=default_documents_dir,
    is_reaper_running=is_reaper_running,
    now=datetime.now,
)


def _home_dir(env: dict[str, str]) -> Path:
    return Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())


def _platform_name() -> str:
    return sys.platform


def _env_map(env: dict[str, str] | None) -> dict[str, str]:
    return dict(os.environ if env is None else env)


def _cwd_path(cwd: str | Path | None) -> Path:
    return Path.cwd() if cwd is None else Path(cwd)


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _default_target(*, platform: str, env: dict[str, str], deps: OperationDeps) -> Path:
    return deps.default_reapack_ini_path(platform=platform, home=_home_dir(env), env=env)


def _default_output_dir(*, platform: str, env: dict[str, str], cwd: Path, deps: OperationDeps) -> Path:
    return deps.default_documents_dir(platform=platform, home=_home_dir(env), cwd=cwd)


def export_repositories(
    *,
    source: str | Path | None,
    output_dir: str | Path | None,
    create_zip: bool,
    keep_folder: bool,
    deps: OperationDeps = DEFAULT_DEPS,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    platform: str | None = None,
) -> ExportResult:
    if keep_folder and not create_zip:
        raise InvalidInputError("--keep-folder can only be used together with --zip.")

    env_map = _env_map(env)
    platform_name = platform or _platform_name()
    current_dir = _cwd_path(cwd)
    source_path = Path(source) if source is not None else _default_target(platform=platform_name, env=env_map, deps=deps)
    if not source_path.is_file():
        raise InvalidInputError(f"Source reapack.ini not found: {source_path}")

    out_dir = Path(output_dir) if output_dir is not None else _default_output_dir(platform=platform_name, env=env_map, cwd=current_dir, deps=deps)
    parsed = deps.parse_remotes(_read_text(source_path))
    if not parsed.remotes:
        raise InvalidInputError("No remotes found in [remotes] section.")

    bundle_dir = out_dir / f"reapack-portable-{deps.now().strftime('%Y%m%d-%H%M%S')}"
    try:
        exported_dir = deps.export_bundle(bundle_dir, parsed.remotes, source=str(source_path))
    except BundleError as exc:
        raise ExportOperationError(str(exc)) from exc
    except OSError as exc:
        raise ExportOperationError(f"Export failed: {exc}") from exc

    zip_path: Path | None = None
    if create_zip:
        try:
            zip_path = deps.create_bundle_zip(exported_dir)
        except BundleError as exc:
            raise ExportOperationError(str(exc)) from exc
        except OSError as exc:
            raise ExportOperationError(f"ZIP creation failed: {exc}") from exc
        if not keep_folder:
            shutil.rmtree(exported_dir)

    return ExportResult(
        repository_count=len(parsed.remotes),
        bundle_path=exported_dir,
        zip_path=zip_path,
    )


def preview_import(
    *,
    bundle: str | Path,
    target: str | Path | None,
    deps: OperationDeps = DEFAULT_DEPS,
    env: dict[str, str] | None = None,
    platform: str | None = None,
) -> ImportPlan:
    env_map = _env_map(env)
    platform_name = platform or _platform_name()
    target_path = Path(target) if target is not None else _default_target(platform=platform_name, env=env_map, deps=deps)
    if not target_path.is_file():
        raise InvalidInputError(f"Target reapack.ini not found: {target_path}")

    try:
        imported = deps.load_bundle_remotes(bundle)
    except (BundleError, FileNotFoundError) as exc:
        raise InvalidInputError(str(exc)) from exc

    existing = deps.parse_remotes(_read_text(target_path))
    merged, added, skipped = deps.merge_remotes(existing.remotes, imported)
    return ImportPlan(
        imported_count=len(imported),
        added_count=added,
        skipped_count=skipped,
        total_count=len(merged),
        repositories=tuple(imported),
    )


def import_repositories(
    *,
    bundle: str | Path,
    target: str | Path | None,
    deps: OperationDeps = DEFAULT_DEPS,
    env: dict[str, str] | None = None,
    platform: str | None = None,
    proc_root: str | Path = "/proc",
    runner=None,
) -> ImportResult:
    env_map = _env_map(env)
    platform_name = platform or _platform_name()
    target_path = Path(target) if target is not None else _default_target(platform=platform_name, env=env_map, deps=deps)
    if not target_path.is_file():
        raise InvalidInputError(f"Target reapack.ini not found: {target_path}")

    try:
        imported = deps.load_bundle_remotes(bundle)
    except (BundleError, FileNotFoundError) as exc:
        raise InvalidInputError(str(exc)) from exc

    try:
        running = deps.is_reaper_running(platform=platform_name, proc_root=proc_root, runner=runner)
    except ProcessDetectionError as exc:
        raise ReaperDetectionError(str(exc)) from exc
    if running:
        raise ReaperRunningError("REAPER is running. Close all REAPER instances before importing repositories.")

    try:
        backup, added, skipped, total = deps.import_remotes(target_path, imported)
    except FileNotFoundError as exc:
        raise InvalidInputError(str(exc)) from exc
    except (BackupError, ImportVerificationError, OSError) as exc:
        raise ImportOperationError(str(exc)) from exc

    return ImportResult(
        target_path=target_path,
        backup_path=backup,
        added_count=added,
        skipped_count=skipped,
        total_count=total,
    )
