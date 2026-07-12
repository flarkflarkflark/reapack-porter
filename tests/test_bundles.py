from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from reapack_porter.bundles import BundleError, export_bundle, load_bundle_remotes
from reapack_porter.core import Remote


def test_export_bundle_writes_expected_files(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle with spaces"
    export_bundle(
        bundle_dir,
        [
            Remote("Zulu", "https://example.com/z", "1", "0"),
            Remote("Alpha", "https://example.com/a", "0", "1"),
        ],
        source="/tmp/O'Hara/reapack.ini",
    )

    assert (bundle_dir / "repos.tsv").read_text(encoding="utf-8") == (
        "Alpha\thttps://example.com/a\t0\t1\n"
        "Zulu\thttps://example.com/z\t1\t0\n"
    )
    assert (bundle_dir / "repos_urls.txt").read_text(encoding="utf-8") == (
        "https://example.com/a\nhttps://example.com/z\n"
    )
    remotes_text = (bundle_dir / "remotes_section.ini").read_text(encoding="utf-8")
    assert "remote0=Alpha|https://example.com/a|0|1" in remotes_text
    assert "remote1=Zulu|https://example.com/z|1|0" in remotes_text
    assert "Close REAPER." in (bundle_dir / "README_IMPORT.txt").read_text(encoding="utf-8")


def test_load_bundle_from_folder(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "remotes_section.ini").write_text(
        "[remotes]\nremote0=Repo|https://example.com/repo|1|0\nsize=1\n",
        encoding="utf-8",
    )
    remotes = load_bundle_remotes(bundle_dir)
    assert remotes == [Remote("Repo", "https://example.com/repo", "1", "0")]


def test_load_bundle_from_zip_root(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "remotes_section.ini",
            "[remotes]\nremote0=Repo|https://example.com/repo|1|0\nsize=1\n",
        )
    remotes = load_bundle_remotes(archive)
    assert remotes == [Remote("Repo", "https://example.com/repo", "1", "0")]


def test_load_bundle_from_zip_nested_folder(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "portable/remotes_section.ini",
            "[remotes]\nremote0=Repo|https://example.com/repo|1|0\nsize=1\n",
        )
    remotes = load_bundle_remotes(archive)
    assert remotes == [Remote("Repo", "https://example.com/repo", "1", "0")]


def test_invalid_zip_without_remotes_section(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("readme.txt", "missing")
    with pytest.raises(BundleError, match="remotes_section.ini"):
        load_bundle_remotes(archive)


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("../remotes_section.ini", "[remotes]\nsize=0\n")
    with pytest.raises(BundleError, match="Unsafe ZIP entry path"):
        load_bundle_remotes(archive)


def test_zip_backslash_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("nested\\..\\remotes_section.ini", "[remotes]\nsize=0\n")
    with pytest.raises(BundleError, match="Unsafe ZIP entry path"):
        load_bundle_remotes(archive)


def test_zip_drive_prefixed_entry_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("C:/bundle/remotes_section.ini", "[remotes]\nsize=0\n")
    with pytest.raises(BundleError, match="Unsafe ZIP entry path"):
        load_bundle_remotes(archive)


def test_folder_bundle_without_remotes_section_fails(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    with pytest.raises(BundleError, match="does not contain remotes_section.ini"):
        load_bundle_remotes(bundle_dir)
