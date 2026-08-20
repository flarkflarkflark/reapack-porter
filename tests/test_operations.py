from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from reapack_porter.operations import (
    DEFAULT_DEPS,
    ExportOperationError,
    ImportOperationError,
    InvalidInputError,
    OperationDeps,
    ReaperDetectionError,
    ReaperRunningError,
    export_repositories,
    import_repositories,
    preview_import,
)
from reapack_porter.core import Remote
from reapack_porter.processes import ProcessDetectionError


def _source_ini(path: Path) -> Path:
    path.write_text(
        "[general]\nversion=4\n\n[remotes]\nremote0=ReaPack|https://reapack.com/index.xml|1|1\nremote1=Other|https://example.com/other|1|0\nsize=2\n",
        encoding="utf-8",
    )
    return path


def _target_ini(path: Path) -> Path:
    path.write_text(
        "[general]\nversion=4\n\n[remotes]\nremote0=Existing|https://reapack.com/index.xml/|1|1\nsize=1\n\n[other]\nvalue=preserve-me\n",
        encoding="utf-8",
    )
    return path


def _cp1252_source_ini(path: Path) -> Path:
    text = (
        "[general]\r\nversion=4\r\n\r\n[remotes]\r\n"
        "remote0=Müller|https://example.com/mueller|1|1\r\n"
        "remote1=Café Repo|https://example.com/cafe|1|0\r\n"
        "size=2\r\n"
    )
    path.write_bytes(text.encode("cp1252"))
    return path


def _cp1252_target_ini(path: Path) -> Path:
    text = (
        "[general]\r\nversion=4\r\n\r\n[remotes]\r\n"
        "remote0=Existing|https://example.com/mueller/|1|1\r\n"
        "size=1\r\n\r\n[other]\r\ndisplay_name=Björk\r\n"
    )
    path.write_bytes(text.encode("cp1252"))
    return path


def test_export_folder_success(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    result = export_repositories(
        source=source,
        output_dir=tmp_path / "out",
        create_zip=False,
        keep_folder=False,
        deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "now": lambda: datetime(2026, 7, 12, 12, 0, 0)}),
        platform="linux",
        env={},
        cwd=tmp_path,
    )
    assert result.repository_count == 2
    assert result.bundle_path.is_dir()
    assert result.zip_path is None


def test_export_zip_success_and_keep_folder_false_removes_bundle(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    result = export_repositories(
        source=source,
        output_dir=tmp_path / "out",
        create_zip=True,
        keep_folder=False,
        deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "now": lambda: datetime(2026, 7, 12, 12, 0, 0)}),
        platform="linux",
        env={},
        cwd=tmp_path,
    )
    assert result.zip_path is not None and result.zip_path.is_file()
    assert not result.bundle_path.exists()


def test_export_zip_keep_folder_true_preserves_bundle(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    result = export_repositories(
        source=source,
        output_dir=tmp_path / "out",
        create_zip=True,
        keep_folder=True,
        deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "now": lambda: datetime(2026, 7, 12, 12, 0, 0)}),
        platform="linux",
        env={},
        cwd=tmp_path,
    )
    assert result.bundle_path.is_dir()
    assert result.zip_path is not None and result.zip_path.is_file()


def test_export_zip_error_keeps_bundle(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    deps = OperationDeps(
        **{
            **DEFAULT_DEPS.__dict__,
            "create_bundle_zip": lambda bundle_dir: (_ for _ in ()).throw(OSError("zip failed")),
            "now": lambda: datetime(2026, 7, 12, 12, 0, 0),
        }
    )
    with pytest.raises(ExportOperationError):
        export_repositories(
            source=source,
            output_dir=tmp_path / "out",
            create_zip=True,
            keep_folder=False,
            deps=deps,
            platform="linux",
            env={},
            cwd=tmp_path,
        )
    bundle_dir = tmp_path / "out" / "reapack-portable-20260712-120000"
    assert bundle_dir.is_dir()


def test_preview_does_not_write_or_backup(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    bundle = export_repositories(
        source=source,
        output_dir=tmp_path / "out",
        create_zip=True,
        keep_folder=True,
        deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "now": lambda: datetime(2026, 7, 12, 12, 0, 0)}),
        platform="linux",
        env={},
        cwd=tmp_path,
    )
    target = _target_ini(tmp_path / "target.ini")
    before = target.read_bytes()
    plan = preview_import(bundle=bundle.zip_path, target=target, platform="linux", env={})
    assert plan.added_count == 1
    assert plan.skipped_count == 1
    assert plan.total_count == 2
    assert target.read_bytes() == before
    assert not list(tmp_path.glob("target.ini.bak.*"))


def test_import_blocks_when_reaper_running(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    bundle = export_repositories(source=source, output_dir=tmp_path / "out", create_zip=False, keep_folder=False, platform="linux", env={}, cwd=tmp_path)
    target = _target_ini(tmp_path / "target.ini")
    before = target.read_bytes()
    deps = OperationDeps(**{**DEFAULT_DEPS.__dict__, "is_reaper_running": lambda **kwargs: True})
    with pytest.raises(ReaperRunningError):
        import_repositories(bundle=bundle.bundle_path, target=target, deps=deps, platform="linux", env={})
    assert target.read_bytes() == before
    assert not list(tmp_path.glob("target.ini.bak.*"))


def test_import_blocks_on_detection_error(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    bundle = export_repositories(source=source, output_dir=tmp_path / "out", create_zip=False, keep_folder=False, platform="linux", env={}, cwd=tmp_path)
    target = _target_ini(tmp_path / "target.ini")
    deps = OperationDeps(
        **{
            **DEFAULT_DEPS.__dict__,
            "is_reaper_running": lambda **kwargs: (_ for _ in ()).throw(ProcessDetectionError("detect failed")),
        }
    )
    with pytest.raises(ReaperDetectionError):
        import_repositories(bundle=bundle.bundle_path, target=target, deps=deps, platform="linux", env={})
    assert not list(tmp_path.glob("target.ini.bak.*"))


def test_successful_import_returns_structured_result(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    bundle = export_repositories(source=source, output_dir=tmp_path / "out", create_zip=True, keep_folder=True, platform="linux", env={}, cwd=tmp_path)
    target = _target_ini(tmp_path / "target.ini")
    result = import_repositories(
        bundle=bundle.zip_path,
        target=target,
        deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "is_reaper_running": lambda **kwargs: False}),
        platform="linux",
        env={},
    )
    assert result.added_count == 1
    assert result.skipped_count == 1
    assert result.backup_path.is_file()
    text = target.read_text(encoding="utf-8")
    assert "[other]" in text and "value=preserve-me" in text
    assert text.count("https://reapack.com/index.xml/") == 1


def test_export_succeeds_with_cp1252_source(tmp_path: Path) -> None:
    source = _cp1252_source_ini(tmp_path / "source.ini")
    result = export_repositories(
        source=source,
        output_dir=tmp_path / "out",
        create_zip=False,
        keep_folder=False,
        deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "now": lambda: datetime(2026, 7, 12, 12, 0, 0)}),
        platform="linux",
        env={},
        cwd=tmp_path,
    )
    assert result.repository_count == 2
    repos_text = (result.bundle_path / "repos.tsv").read_text(encoding="utf-8")
    assert "Müller" in repos_text
    assert "Café Repo" in repos_text


def test_export_raises_invalid_input_for_undecodable_source(tmp_path: Path) -> None:
    source = tmp_path / "source.ini"
    source.write_bytes(b"[remotes]\n\x81\nsize=0\n")
    with pytest.raises(InvalidInputError):
        export_repositories(
            source=source,
            output_dir=tmp_path / "out",
            create_zip=False,
            keep_folder=False,
            platform="linux",
            env={},
            cwd=tmp_path,
        )


def test_preview_import_succeeds_with_cp1252_target(tmp_path: Path) -> None:
    source = _cp1252_source_ini(tmp_path / "source.ini")
    bundle = export_repositories(
        source=source, output_dir=tmp_path / "out", create_zip=True, keep_folder=True, platform="linux", env={}, cwd=tmp_path
    )
    target = _cp1252_target_ini(tmp_path / "target.ini")
    plan = preview_import(bundle=bundle.zip_path, target=target, platform="linux", env={})
    assert plan.imported_count == 2
    assert plan.added_count == 1
    assert plan.skipped_count == 1
    assert plan.total_count == 2


def test_real_import_succeeds_with_cp1252_target_and_preserves_other_content(tmp_path: Path) -> None:
    source = _cp1252_source_ini(tmp_path / "source.ini")
    bundle = export_repositories(
        source=source, output_dir=tmp_path / "out", create_zip=True, keep_folder=True, platform="linux", env={}, cwd=tmp_path
    )
    target = _cp1252_target_ini(tmp_path / "target.ini")
    original_bytes = target.read_bytes()

    result = import_repositories(
        bundle=bundle.zip_path,
        target=target,
        deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "is_reaper_running": lambda **kwargs: False}),
        platform="linux",
        env={},
    )

    assert result.added_count == 1
    assert result.skipped_count == 1
    assert result.total_count == 2
    assert result.backup_path.read_bytes() == original_bytes

    written_text = target.read_bytes().decode("cp1252")
    assert "display_name=Björk" in written_text
    assert "remote0=Existing|https://example.com/mueller/|1|1" in written_text
    assert "remote1=Café Repo|https://example.com/cafe|1|0" in written_text


def test_real_import_raises_invalid_input_for_undecodable_target(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    bundle = export_repositories(source=source, output_dir=tmp_path / "out", create_zip=False, keep_folder=False, platform="linux", env={}, cwd=tmp_path)
    target = tmp_path / "target.ini"
    target.write_bytes(b"[remotes]\n\x81\nsize=0\n")
    with pytest.raises(InvalidInputError):
        import_repositories(
            bundle=bundle.bundle_path,
            target=target,
            deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "is_reaper_running": lambda **kwargs: False}),
            platform="linux",
            env={},
        )


def test_real_import_keeps_utf8_encoding_without_introducing_bom(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    bundle = export_repositories(source=source, output_dir=tmp_path / "out", create_zip=False, keep_folder=False, platform="linux", env={}, cwd=tmp_path)
    target = _target_ini(tmp_path / "target.ini")
    import_repositories(
        bundle=bundle.bundle_path,
        target=target,
        deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "is_reaper_running": lambda **kwargs: False}),
        platform="linux",
        env={},
    )
    assert not target.read_bytes().startswith(b"\xef\xbb\xbf")


def test_real_import_preserves_utf8_bom_target(tmp_path: Path) -> None:
    source = _source_ini(tmp_path / "source.ini")
    bundle = export_repositories(source=source, output_dir=tmp_path / "out", create_zip=False, keep_folder=False, platform="linux", env={}, cwd=tmp_path)
    target = tmp_path / "target.ini"
    original_text = "[general]\nversion=4\n\n[remotes]\nremote0=Existing|https://example.com/existing|1|1\nsize=1\n"
    original_bytes = original_text.encode("utf-8-sig")
    target.write_bytes(original_bytes)

    result = import_repositories(
        bundle=bundle.bundle_path,
        target=target,
        deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "is_reaper_running": lambda **kwargs: False}),
        platform="linux",
        env={},
    )

    written = target.read_bytes()
    assert written.startswith(b"\xef\xbb\xbf")
    assert written.count(b"\xef\xbb\xbf") == 1
    assert result.backup_path.read_bytes() == original_bytes


def test_end_to_end_cp1252_smoke(tmp_path: Path) -> None:
    target = _cp1252_target_ini(tmp_path / "reapack.ini")
    original_bytes = target.read_bytes()
    source = _cp1252_source_ini(tmp_path / "source.ini")

    export = export_repositories(
        source=source,
        output_dir=tmp_path / "out",
        create_zip=True,
        keep_folder=True,
        platform="linux",
        env={},
        cwd=tmp_path,
    )

    plan = preview_import(bundle=export.zip_path, target=target, platform="linux", env={})
    assert plan.added_count == 1
    assert plan.skipped_count == 1

    result = import_repositories(
        bundle=export.zip_path,
        target=target,
        deps=OperationDeps(**{**DEFAULT_DEPS.__dict__, "is_reaper_running": lambda **kwargs: False}),
        platform="linux",
        env={},
    )
    assert result.added_count == 1
    assert result.skipped_count == 1
    assert result.total_count == 2
    assert result.backup_path.read_bytes() == original_bytes

    written_text = target.read_bytes().decode("cp1252")
    assert "remote0=Existing|https://example.com/mueller/|1|1" in written_text
    assert "remote1=Café Repo|https://example.com/cafe|1|0" in written_text
    assert "display_name=Björk" in written_text


def test_real_import_raises_invalid_input_when_target_encoding_cannot_represent_import(tmp_path: Path) -> None:
    target = _cp1252_target_ini(tmp_path / "target.ini")
    original_bytes = target.read_bytes()

    deps = OperationDeps(
        **{
            **DEFAULT_DEPS.__dict__,
            "is_reaper_running": lambda **kwargs: False,
            "load_bundle_remotes": lambda bundle: [
                Remote("日本語 Repository", "https://example.com/unicode", "1", "0")
            ],
        }
    )

    with pytest.raises(InvalidInputError) as excinfo:
        import_repositories(bundle="unused-bundle", target=target, deps=deps, platform="linux", env={})

    assert "cp1252" in str(excinfo.value)
    assert target.read_bytes() == original_bytes
    assert not list(tmp_path.glob("target.ini.bak.*"))
    assert not list(tmp_path.glob("target.ini.tmp.*"))
