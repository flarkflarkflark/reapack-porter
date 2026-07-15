from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import sys
from typing import Any, Callable

from .operations import (
    DEFAULT_DEPS,
    ExportOperationError,
    ExportResult,
    ImportOperationError,
    ImportPlan,
    ImportResult,
    InvalidInputError,
    ReaperDetectionError,
    ReaperRunningError,
    export_repositories,
    import_repositories,
    preview_import,
)


EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_REAPER_RUNNING = 3
EXIT_INVALID_INPUT = 4
EXIT_OPERATIONAL_ERROR = 5
EXIT_INTERNAL_ERROR = 6


Operation = Callable[..., Any]


@dataclass(frozen=True)
class CliDeps:
    export_repositories: Operation
    preview_import: Operation
    import_repositories: Operation


DEFAULT_DEPS = CliDeps(
    export_repositories=export_repositories,
    preview_import=preview_import,
    import_repositories=import_repositories,
)


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
def _run_export(args: argparse.Namespace, *, deps: CliDeps, stdout, env: dict[str, str], cwd, platform: str) -> int:
    result: ExportResult = deps.export_repositories(
        source=args.source,
        output_dir=args.out,
        create_zip=args.zip,
        keep_folder=args.keep_folder,
        env=env,
        cwd=cwd,
        platform=platform,
    )
    print(f"Repositories: {result.repository_count}", file=stdout)
    print(f"Export folder: {result.bundle_path}", file=stdout)
    if result.zip_path is not None:
        print(f"ZIP: {result.zip_path}", file=stdout)
        if not args.keep_folder:
            print(f"Removed export folder: {result.bundle_path}", file=stdout)
    return EXIT_SUCCESS


def _run_import(args: argparse.Namespace, *, deps: CliDeps, stdout, env: dict[str, str], platform: str) -> int:
    if args.dry_run:
        plan: ImportPlan = deps.preview_import(
            bundle=args.bundle,
            target=args.target,
            env=env,
            platform=platform,
        )
        print(f"Bundle repositories: {plan.imported_count}", file=stdout)
        print(f"Would add: {plan.added_count}", file=stdout)
        print(f"Would skip existing: {plan.skipped_count}", file=stdout)
        print(f"Expected total: {plan.total_count}", file=stdout)
        return EXIT_SUCCESS

    result: ImportResult = deps.import_repositories(
        bundle=args.bundle,
        target=args.target,
        env=env,
        platform=platform,
    )
    print(f"Target: {result.target_path}", file=stdout)
    print(f"Backup: {result.backup_path}", file=stdout)
    print(f"Added: {result.added_count}", file=stdout)
    print(f"Skipped: {result.skipped_count}", file=stdout)
    print(f"Total: {result.total_count}", file=stdout)
    return EXIT_SUCCESS


def main(
    argv: list[str] | None = None,
    *,
    deps: CliDeps = DEFAULT_DEPS,
    stdout=None,
    stderr=None,
    env: dict[str, str] | None = None,
    cwd=None,
    platform: str | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    env_map = dict(os.environ if env is None else env)
    current_dir = cwd
    platform_name = platform or sys.platform
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
    except (ReaperDetectionError,) as exc:
        print(str(exc), file=stderr)
        return EXIT_REAPER_RUNNING
    except (ReaperRunningError,) as exc:
        print(str(exc), file=stderr)
        return EXIT_REAPER_RUNNING
    except (InvalidInputError,) as exc:
        print(str(exc), file=stderr)
        return EXIT_INVALID_INPUT
    except (ExportOperationError, ImportOperationError) as exc:
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
