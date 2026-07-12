from __future__ import annotations

from io import StringIO
from pathlib import Path

from reapack_porter.cli import (
    CliDeps,
    EXIT_INVALID_INPUT,
    EXIT_REAPER_RUNNING,
    EXIT_SUCCESS,
    build_parser,
    main,
)
from reapack_porter.operations import ExportResult, ImportPlan, ImportResult


def make_deps(tmp_path: Path) -> CliDeps:
    return CliDeps(
        export_repositories=None,
        preview_import=None,
        import_repositories=None,
    )


def test_build_parser_supports_help() -> None:
    parser = build_parser()
    assert parser.prog == "reapack-porter"


def test_cli_export_reports_folder_and_zip(tmp_path: Path) -> None:
    source = tmp_path / "source.ini"
    source.write_text("[remotes]\nremote0=Repo|https://example.com/repo|1|0\nsize=1\n", encoding="utf-8")
    bundle_dir = tmp_path / "reapack-portable-20260712-120000"
    zip_path = tmp_path / "reapack-portable-20260712-120000.zip"
    stdout = StringIO()
    stderr = StringIO()

    deps = make_deps(tmp_path)
    deps = CliDeps(
        export_repositories=lambda **kwargs: ExportResult(1, bundle_dir, zip_path),
        preview_import=deps.preview_import,
        import_repositories=deps.import_repositories,
    )

    code = main(
        ["export", "--source", str(source), "--zip", "--keep-folder"],
        deps=deps,
        stdout=stdout,
        stderr=stderr,
        env={},
        cwd=tmp_path,
        platform="linux",
    )

    assert code == EXIT_SUCCESS
    assert "Repositories: 1" in stdout.getvalue()
    assert f"ZIP: {zip_path}" in stdout.getvalue()


def test_cli_import_dry_run_reports_counts(tmp_path: Path) -> None:
    target = tmp_path / "reapack.ini"
    target.write_text("[remotes]\nremote0=Existing|https://example.com/existing|1|0\nsize=1\n", encoding="utf-8")
    stdout = StringIO()
    deps = CliDeps(
        export_repositories=None,
        preview_import=lambda **kwargs: ImportPlan(
            imported_count=2,
            added_count=1,
            skipped_count=1,
            total_count=2,
            repositories=(),
        ),
        import_repositories=None,
    )

    code = main(
        ["import", "--bundle", str(tmp_path / "bundle.zip"), "--dry-run"],
        deps=deps,
        stdout=stdout,
        stderr=StringIO(),
        env={},
        cwd=tmp_path,
        platform="linux",
    )
    assert code == EXIT_SUCCESS
    assert "Would add: 1" in stdout.getvalue()
    assert "Expected total: 2" in stdout.getvalue()


def test_cli_import_blocks_when_reaper_running(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    deps = CliDeps(
        export_repositories=None,
        preview_import=None,
        import_repositories=lambda **kwargs: (_ for _ in ()).throw(
            __import__("reapack_porter.operations", fromlist=["ReaperRunningError"]).ReaperRunningError(
                "REAPER is running. Close all REAPER instances before importing repositories."
            )
        ),
    )

    code = main(
        ["import", "--bundle", str(tmp_path / "bundle.zip")],
        deps=deps,
        stdout=stdout,
        stderr=stderr,
        env={},
        cwd=tmp_path,
        platform="linux",
    )
    assert code == EXIT_REAPER_RUNNING
    assert "REAPER is running." in stderr.getvalue()


def test_cli_import_reports_success(tmp_path: Path) -> None:
    stdout = StringIO()
    deps = CliDeps(
        export_repositories=None,
        preview_import=None,
        import_repositories=lambda **kwargs: ImportResult(
            target_path=tmp_path / "reapack.ini",
            backup_path=tmp_path / "reapack.ini.bak.20260712-120000",
            added_count=1,
            skipped_count=0,
            total_count=1,
        ),
    )

    code = main(
        ["import", "--bundle", str(tmp_path / "bundle.zip")],
        deps=deps,
        stdout=stdout,
        stderr=StringIO(),
        env={},
        cwd=tmp_path,
        platform="linux",
    )
    assert code == EXIT_SUCCESS
    assert "Added: 1" in stdout.getvalue()


def test_cli_rejects_keep_folder_without_zip(tmp_path: Path) -> None:
    source = tmp_path / "source.ini"
    source.write_text("[remotes]\nremote0=Repo|https://example.com/repo|1|0\nsize=1\n", encoding="utf-8")
    deps = CliDeps(
        export_repositories=lambda **kwargs: (_ for _ in ()).throw(
            __import__("reapack_porter.operations", fromlist=["InvalidInputError"]).InvalidInputError(
                "--keep-folder can only be used together with --zip."
            )
        ),
        preview_import=None,
        import_repositories=None,
    )
    code = main(
        ["export", "--source", str(source), "--keep-folder"],
        deps=deps,
        stdout=StringIO(),
        stderr=StringIO(),
        env={},
        cwd=tmp_path,
        platform="linux",
    )
    assert code == EXIT_INVALID_INPUT


def test_cli_import_returns_reaper_exit_code_on_detection_error(tmp_path: Path) -> None:
    stderr = StringIO()
    deps = CliDeps(
        export_repositories=None,
        preview_import=None,
        import_repositories=lambda **kwargs: (_ for _ in ()).throw(
            __import__("reapack_porter.operations", fromlist=["ReaperDetectionError"]).ReaperDetectionError("detect failed")
        ),
    )
    code = main(
        ["import", "--bundle", str(tmp_path / "bundle.zip")],
        deps=deps,
        stdout=StringIO(),
        stderr=stderr,
        env={},
        cwd=tmp_path,
        platform="linux",
    )
    assert code == EXIT_REAPER_RUNNING
    assert "detect failed" in stderr.getvalue()


def test_cli_returns_invalid_input_for_missing_source(tmp_path: Path) -> None:
    deps = CliDeps(
        export_repositories=lambda **kwargs: (_ for _ in ()).throw(
            __import__("reapack_porter.operations", fromlist=["InvalidInputError"]).InvalidInputError(
                f"Source reapack.ini not found: {tmp_path / 'missing.ini'}"
            )
        ),
        preview_import=None,
        import_repositories=None,
    )
    code = main(
        ["export", "--source", str(tmp_path / "missing.ini")],
        deps=deps,
        stdout=StringIO(),
        stderr=StringIO(),
        env={},
        cwd=tmp_path,
        platform="linux",
    )
    assert code == EXIT_INVALID_INPUT
