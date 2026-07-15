from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_readme_documents_current_standalone_app() -> None:
    text = _read("README.md")
    lower = text.lower()
    assert "not available yet" not in lower
    assert "planned standalone application" not in lower
    assert "linux" in lower
    assert "windows" in lower
    assert "macos" in lower
    assert "x86_64" in text
    assert "arm64" in text
    assert "Close all REAPER processes" in text
    assert "Export is read-only and may be used while REAPER is running." in text
    assert "timestamped backup" in lower
    for flag in ("--source", "--out", "--bundle", "--target", "--dry-run"):
        assert flag in text
    assert "--ignore-reaper" not in text


def test_readme_documents_bundle_checksums_signing_and_legacy_lua() -> None:
    text = _read("README.md")
    for filename in ("repos.tsv", "repos_urls.txt", "remotes_section.ini", "README_IMPORT.txt"):
        assert filename in text
    assert "sha256sum -c ReaPack-Porter-0.1.0-linux-x86_64.tar.gz.sha256" in text
    assert "shasum -a 256 -c ReaPack-Porter-0.1.0-macos-arm64.zip.sha256" in text
    assert "Windows builds are not digitally signed yet" in text
    assert "macOS builds are not codesigned or notarized yet" in text
    assert "reapack_porter.lua" in text
    assert "Legacy ReaScript Screenshots" in text


def test_release_documents_exist_and_reference_version() -> None:
    for relative in ("CHANGELOG.md", "docs/release-notes/v0.1.0.md", "docs/RELEASING.md"):
        assert (ROOT / relative).is_file()
        assert "0.1.0" in _read(relative)


def test_release_notes_list_exact_archives() -> None:
    text = _read("docs/release-notes/v0.1.0.md")
    for filename in [
        "ReaPack-Porter-0.1.0-linux-x86_64.tar.gz",
        "ReaPack-Porter-0.1.0-windows-x86_64.zip",
        "ReaPack-Porter-0.1.0-macos-x86_64.zip",
        "ReaPack-Porter-0.1.0-macos-arm64.zip",
    ]:
        assert filename in text
    assert "Close REAPER completely before importing." in text
    assert "Windows and macOS builds are unsigned." in text
    assert "macOS builds are not notarized." in text


def test_releasing_document_describes_draft_only_annotated_tag_flow() -> None:
    text = _read("docs/RELEASING.md")
    lower = text.lower()
    assert "git tag -a v0.1.0" in text
    assert "draft github release" in lower
    assert "not published automatically" in lower or "not publish" in lower
    assert "Never tag from a dirty local `main` checkout." in text
    assert "Signing, notarization, DMG, MSI and auto-update are not part of v0.1.0." in text
