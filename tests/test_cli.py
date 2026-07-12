from __future__ import annotations

from io import StringIO
from pathlib import Path

from reapack_porter.cli import (
    CliDeps,
    EXIT_INVALID_INPUT,
    EXIT_OPERATIONAL_ERROR,
    EXIT_REAPER_RUNNING,
    EXIT_SUCCESS,
    build_parser,
    main,
)
from reapack_porter.core import Remote


def make_deps(tmp_path: Path) -> CliDeps:
    def fake_default_ini_path(*, platform: str, home: Path, env: dict[str, str]) -> Path:
        del platform, home, env
        return tmp_path / "reapack.ini"

    def fake_default_documents_dir(*, platform: str, home: Path, cwd: Path) -> Path:
        del platform, home, cwd
        return tmp_path

    return CliDeps(
        export_bundle=None,
        create_bundle_zip=None,
        load_bundle_remotes=None,
        import_remotes=None,
        default_reapack_ini_path=fake_default_ini_path,
        default_documents_dir=fake_default_documents_dir,
        is_reaper_running=None,
        parse_remotes=None,
        merge_remotes=None,
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
        export_bundle=lambda path, remotes, source: bundle_dir,
        create_bundle_zip=lambda path: zip_path,
        load_bundle_remotes=deps.load_bundle_remotes,
        import_remotes=deps.import_remotes,
        default_reapack_ini_path=deps.default_reapack_ini_path,
        default_documents_dir=deps.default_documents_dir,
        is_reaper_running=lambda **kwargs: False,
        parse_remotes=lambda text: type("Parsed", (), {"remotes": [Remote("Repo", "https://example.com/repo", "1", "0")]}),
        merge_remotes=deps.merge_remotes,
    )
    bundle_dir.mkdir()

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
    deps = make_deps(tmp_path)
    deps = CliDeps(
        export_bundle=deps.export_bundle,
        create_bundle_zip=deps.create_bundle_zip,
        load_bundle_remotes=lambda bundle: [
            Remote("Existing", "https://example.com/existing/", "1", "0"),
            Remote("New", "https://example.com/new", "1", "1"),
        ],
        import_remotes=deps.import_remotes,
        default_reapack_ini_path=deps.default_reapack_ini_path,
        default_documents_dir=deps.default_documents_dir,
        is_reaper_running=lambda **kwargs: False,
        parse_remotes=lambda text: type(
            "Parsed",
            (),
            {"remotes": [Remote("Existing", "https://example.com/existing", "1", "0")]},
        ),
        merge_remotes=lambda existing, imported: (
            [existing[0], imported[1]],
            1,
            1,
        ),
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
    deps = make_deps(tmp_path)
    deps = CliDeps(
        export_bundle=deps.export_bundle,
        create_bundle_zip=deps.create_bundle_zip,
        load_bundle_remotes=lambda bundle: [],
        import_remotes=lambda target, remotes: None,
        default_reapack_ini_path=deps.default_reapack_ini_path,
        default_documents_dir=deps.default_documents_dir,
        is_reaper_running=lambda **kwargs: True,
        parse_remotes=lambda text: None,
        merge_remotes=lambda existing, imported: None,
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
    deps = make_deps(tmp_path)
    deps = CliDeps(
        export_bundle=deps.export_bundle,
        create_bundle_zip=deps.create_bundle_zip,
        load_bundle_remotes=lambda bundle: [Remote("Repo", "https://example.com/repo", "1", "0")],
        import_remotes=lambda target, remotes: (tmp_path / "reapack.ini.bak.20260712-120000", 1, 0, 1),
        default_reapack_ini_path=deps.default_reapack_ini_path,
        default_documents_dir=deps.default_documents_dir,
        is_reaper_running=lambda **kwargs: False,
        parse_remotes=lambda text: None,
        merge_remotes=lambda existing, imported: None,
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
    deps = make_deps(tmp_path)
    deps = CliDeps(
        export_bundle=lambda path, remotes, source: path,
        create_bundle_zip=lambda path: path,
        load_bundle_remotes=deps.load_bundle_remotes,
        import_remotes=deps.import_remotes,
        default_reapack_ini_path=deps.default_reapack_ini_path,
        default_documents_dir=deps.default_documents_dir,
        is_reaper_running=lambda **kwargs: False,
        parse_remotes=lambda text: type("Parsed", (), {"remotes": [Remote("Repo", "https://example.com/repo", "1", "0")]}),
        merge_remotes=deps.merge_remotes,
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
    deps = make_deps(tmp_path)
    deps = CliDeps(
        export_bundle=deps.export_bundle,
        create_bundle_zip=deps.create_bundle_zip,
        load_bundle_remotes=lambda bundle: [Remote("Repo", "https://example.com/repo", "1", "0")],
        import_remotes=lambda target, remotes: (tmp_path / "backup", 1, 0, 1),
        default_reapack_ini_path=deps.default_reapack_ini_path,
        default_documents_dir=deps.default_documents_dir,
        is_reaper_running=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("should not be used")),
        parse_remotes=lambda text: None,
        merge_remotes=lambda existing, imported: None,
    )

    from reapack_porter.processes import ProcessDetectionError

    deps = CliDeps(
        export_bundle=deps.export_bundle,
        create_bundle_zip=deps.create_bundle_zip,
        load_bundle_remotes=deps.load_bundle_remotes,
        import_remotes=deps.import_remotes,
        default_reapack_ini_path=deps.default_reapack_ini_path,
        default_documents_dir=deps.default_documents_dir,
        is_reaper_running=lambda **kwargs: (_ for _ in ()).throw(ProcessDetectionError("detect failed")),
        parse_remotes=deps.parse_remotes,
        merge_remotes=deps.merge_remotes,
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
    deps = make_deps(tmp_path)
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
