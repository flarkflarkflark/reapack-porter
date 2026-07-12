from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from reapack_porter.core import (
    ImportVerificationError,
    IniFormatError,
    Remote,
    backup_path_for,
    import_remotes,
    merge_remotes,
    normalize_url,
    parse_remotes,
    remove_remotes_section,
    render_remotes_section,
    replace_remotes_section,
)


def test_parse_missing_remotes_section() -> None:
    parsed = parse_remotes("[general]\nversion=4\n")
    assert parsed.section_present is False
    assert parsed.declared_size is None
    assert parsed.remotes == []


def test_parse_single_and_multiple_repositories_with_crlf() -> None:
    text = (
        "[general]\r\nversion=4\r\n\r\n[remotes]\r\n"
        "remote0=Main Repo|https://example.com/A|1|0\r\n"
        "remote1=Unicode Café|https://example.com/B|0|1\r\n"
        "size=2\r\n"
    )
    parsed = parse_remotes(text)
    assert parsed.section_present is True
    assert parsed.declared_size == 2
    assert parsed.remotes == [
        Remote("Main Repo", "https://example.com/A", "1", "0"),
        Remote("Unicode Café", "https://example.com/B", "0", "1"),
    ]


def test_parse_invalid_remote_line_raises() -> None:
    with pytest.raises(IniFormatError):
        parse_remotes("[remotes]\nremote0=broken|https://example.com|1\nsize=1\n")


def test_normalize_url_trims_case_and_trailing_slash() -> None:
    assert normalize_url("  HTTPS://Example.com/Repo/  ") == "https://example.com/repo"


def test_merge_skips_duplicates_by_case_and_trailing_slash() -> None:
    existing = [Remote("One", "https://Example.com/repo/", "1", "0")]
    imported = [
        Remote("Duplicate", "https://example.com/REPO", "1", "1"),
        Remote("New", "https://example.com/new", "1", "0"),
    ]
    merged, added, skipped = merge_remotes(existing, imported)
    assert merged == [existing[0], imported[1]]
    assert added == 1
    assert skipped == 1


def test_render_remotes_section_is_deterministic() -> None:
    remotes = [
        Remote("Apostrophe's Repo", "https://example.com/a", "1", "0"),
        Remote("Space Repo", "https://example.com/b", "0", "1"),
    ]
    assert render_remotes_section(remotes) == (
        "[remotes]\n"
        "remote0=Apostrophe's Repo|https://example.com/a|1|0\n"
        "remote1=Space Repo|https://example.com/b|0|1\n"
        "size=2\n"
    )


def test_remove_and_replace_remotes_section_preserves_other_sections() -> None:
    text = (
        "[general]\nversion=4\n\n[remotes]\nremote0=Old|https://old|1|0\nsize=1\n\n"
        "[extra]\npath=C:\\Program Files\\O'Hara\n"
    )
    replaced = replace_remotes_section(
        text,
        [Remote("New", "https://new", "1", "1")],
    )
    assert "[extra]\npath=C:\\Program Files\\O'Hara\n" in replaced
    assert "remote0=New|https://new|1|1" in replaced
    assert "remote0=Old|https://old|1|0" not in replaced
    assert remove_remotes_section(text).startswith("[general]\nversion=4")


def test_replace_adds_remotes_when_missing() -> None:
    updated = replace_remotes_section(
        "[general]\nversion=4\n",
        [Remote("Repo", "https://example.com/repo", "1", "0")],
    )
    assert updated.endswith("size=1\n")
    assert "[general]\nversion=4\n\n[remotes]\n" in updated


def test_backup_path_suffix_when_existing_file_conflicts(tmp_path: Path) -> None:
    target = tmp_path / "reapack.ini"
    target.write_text("x", encoding="utf-8")
    first = tmp_path / "reapack.ini.bak.20260712-100000"
    first.write_text("backup", encoding="utf-8")
    path = backup_path_for(target, now=datetime(2026, 7, 12, 10, 0, 0))
    assert path.name == "reapack.ini.bak.20260712-100000-1"


def test_import_remotes_creates_backup_and_verifies_write(tmp_path: Path) -> None:
    target = tmp_path / "reapack.ini"
    target.write_text(
        "[general]\nversion=4\n\n[remotes]\nremote0=One|https://example.com/one|1|0\nsize=1\n",
        encoding="utf-8",
    )
    imported = [
        Remote("One duplicate", "https://EXAMPLE.com/one/", "1", "0"),
        Remote("Two", "https://example.com/two", "1", "1"),
    ]
    backup, added, skipped, total = import_remotes(
        target,
        imported,
        now=datetime(2026, 7, 12, 10, 0, 0),
    )

    assert backup.name == "reapack.ini.bak.20260712-100000"
    assert backup.read_text(encoding="utf-8") == (
        "[general]\nversion=4\n\n[remotes]\nremote0=One|https://example.com/one|1|0\nsize=1\n"
    )
    assert added == 1
    assert skipped == 1
    assert total == 2
    text = target.read_text(encoding="utf-8")
    assert "remote1=Two|https://example.com/two|1|1" in text
    assert not list(tmp_path.glob("reapack.ini.tmp.*"))


def test_import_remotes_requires_existing_target(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        import_remotes(tmp_path / "missing.ini", [])


def test_import_verification_failure_removes_temp_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "reapack.ini"
    target.write_text("[general]\nversion=4\n", encoding="utf-8")

    from io import StringIO

    original_open = Path.open
    call_count = {"value": 0}

    def fake_open(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if self == target:
            call_count["value"] += 1
            if call_count["value"] == 2:
                return StringIO("[general]\nversion=4\n[remotes]\nsize=0\n")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)

    with pytest.raises(ImportVerificationError):
        import_remotes(
            target,
            [Remote("Repo", "https://example.com/repo", "1", "0")],
            now=datetime(2026, 7, 12, 10, 0, 0),
        )
    assert not list(tmp_path.glob("reapack.ini.tmp.*"))
