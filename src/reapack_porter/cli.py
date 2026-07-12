from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Callable

from .bundles import BundleError, create_bundle_zip, export_bundle, load_bundle_remotes
from .core import BackupError, ImportVerificationError, merge_remotes, parse_remotes, import_remotes
from .paths import default_documents_dir, default_reapack_ini_path
from .processes import ProcessDetectionError, is_reaper_running


EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_REAPER_RUNNING = 3
EXIT_INVALID_INPUT = 4
EXIT_OPERATIONAL_ERROR = 5
EXIT_INTERNAL_ERROR = 6


Operation = Callable[..., Any]


@dataclass(frozen=True)
class CliDeps:
    export_bundle: Operation
    create_bundle_zip: Operation
    load_bundle_remotes: Operation
    import_remotes: Operation
    default_reapack_ini_path: Operation
    default_documents_dir: Operation
    is_reaper_running: Operation
    parse_remotes: Operation
    merge_remotes: Operation


DEFAULT_DEPS = CliDeps(
    export_bundle=export_bundle,
    create_bundle_zip=create_bundle_zip,
    load_bundle_remotes=load_bundle_remotes,
    import_remotes=import_remotes,
    default_reapack_ini_path=default_reapack_ini_path,
    default_documents_dir=default_documents_dir,
    is_reaper_running=is_reaper_running,
    parse_remotes=parse_remotes,
    merge_remotes=merge_remotes,
)


def _platform_name() -> str:
    return sys.platform


def _home_dir(env: dict[str, str]) -> Path:
    return Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reapack-porter")
    parser.add_argument("--debug", action="store_true", help="show tracebacks for unexpected errors")

    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="export ReaPack repositories")
    export_parser.add_argument("--source", help="path to source reapack.ini")
    export_parser.add_argument("--out", help="output folder")
    export_parser.add_argument("--zip", action="store_true", help="create a portable ZIP bundle")
    export_parser.add_argument(
        "--keep-folder",
        action="store_true",
        help="keep the bundle folder after ZIP creation succeeds",
    )

    import_parser = subparsers.add_parser("import", help="import ReaPack repositories")
    import_parser.add_argument("--bundle", required=True, help="bundle folder or bundle ZIP")
    import_parser.add_argument("--target", help="path to target reapack.ini")
    import_parser.add_argument("--dry-run", action="store_true", help="analyze import without writing")

    return parser


def _default_output_dir(*, platform: str, env: dict[str, str], cwd: Path, deps: CliDeps) -> Path:
    return deps.default_documents_dir(platform=platform, home=_home_dir(env), cwd=cwd)


def _default_reapack_ini(*, platform: str, env: dict[str, str], deps: CliDeps) -> Path:
    return deps.default_reapack_ini_path(platform=platform, home=_home_dir(env), env=env)


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _run_export(args: argparse.Namespace, *, deps: CliDeps, stdout, env: dict[str, str], cwd: Path, platform: str) -> int:
    if args.keep_folder and not args.zip:
        raise ValueError("--keep-folder can only be used together with --zip.")

    source = Path(args.source) if args.source else _default_reapack_ini(platform=platform, env=env, deps=deps)
    if not source.is_file():
        raise FileNotFoundError(f"Source reapack.ini not found: {source}")

    out_dir = Path(args.out) if args.out else _default_output_dir(platform=platform, env=env, cwd=cwd, deps=deps)
    ini_text = _read_text(source)
    parsed = deps.parse_remotes(ini_text)
    if not parsed.remotes:
        raise BundleError("No remotes found in [remotes] section.")

    bundle_dir = out_dir / f"reapack-portable-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    exported_dir = deps.export_bundle(bundle_dir, parsed.remotes, source=str(source))
    print(f"Repositories: {len(parsed.remotes)}", file=stdout)
    print(f"Export folder: {exported_dir}", file=stdout)

    if args.zip:
        zip_path = deps.create_bundle_zip(exported_dir)
        print(f"ZIP: {zip_path}", file=stdout)
        if not args.keep_folder:
            shutil.rmtree(exported_dir)
            print(f"Removed export folder: {exported_dir}", file=stdout)
    return EXIT_SUCCESS


def _run_import(args: argparse.Namespace, *, deps: CliDeps, stdout, env: dict[str, str], platform: str) -> int:
    bundle_path = Path(args.bundle)
    target = Path(args.target) if args.target else _default_reapack_ini(platform=platform, env=env, deps=deps)
    if args.dry_run:
        imported_remotes = deps.load_bundle_remotes(bundle_path)
        if not target.is_file():
            raise FileNotFoundError(f"Target reapack.ini not found: {target}")
        existing = deps.parse_remotes(_read_text(target))
        merged, added, skipped = deps.merge_remotes(existing.remotes, imported_remotes)
        print(f"Bundle repositories: {len(imported_remotes)}", file=stdout)
        print(f"Would add: {added}", file=stdout)
        print(f"Would skip existing: {skipped}", file=stdout)
        print(f"Expected total: {len(merged)}", file=stdout)
        return EXIT_SUCCESS

    running = deps.is_reaper_running(platform=platform)
    if running:
        raise RuntimeError("REAPER is running. Close all REAPER instances before importing repositories.")

    imported_remotes = deps.load_bundle_remotes(bundle_path)
    backup, added, skipped, total = deps.import_remotes(target, imported_remotes)
    print(f"Target: {target}", file=stdout)
    print(f"Backup: {backup}", file=stdout)
    print(f"Added: {added}", file=stdout)
    print(f"Skipped: {skipped}", file=stdout)
    print(f"Total: {total}", file=stdout)
    return EXIT_SUCCESS


def main(
    argv: list[str] | None = None,
    *,
    deps: CliDeps = DEFAULT_DEPS,
    stdout=None,
    stderr=None,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    platform: str | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    env_map = dict(os.environ if env is None else env)
    current_dir = Path.cwd() if cwd is None else Path(cwd)
    platform_name = platform or _platform_name()
    parser = build_parser()

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        if args.command == "export":
            return _run_export(args, deps=deps, stdout=stdout, env=env_map, cwd=current_dir, platform=platform_name)
        if args.command == "import":
            return _run_import(args, deps=deps, stdout=stdout, env=env_map, platform=platform_name)
        parser.error(f"Unknown command: {args.command}")
    except SystemExit as exc:
        return int(exc.code)
    except ProcessDetectionError as exc:
        print(str(exc), file=stderr)
        return EXIT_REAPER_RUNNING
    except RuntimeError as exc:
        if str(exc).startswith("REAPER is running."):
            print(str(exc), file=stderr)
            return EXIT_REAPER_RUNNING
        print(str(exc), file=stderr)
        return EXIT_OPERATIONAL_ERROR
    except (FileNotFoundError, BundleError, ValueError) as exc:
        print(str(exc), file=stderr)
        return EXIT_INVALID_INPUT
    except (BackupError, ImportVerificationError, OSError) as exc:
        print(str(exc), file=stderr)
        return EXIT_OPERATIONAL_ERROR
    except Exception as exc:
        if getattr(args, "debug", False):
            raise
        print(f"Unexpected error: {exc}", file=stderr)
        return EXIT_INTERNAL_ERROR
    return EXIT_SUCCESS


def console_main() -> None:
    raise SystemExit(main())
