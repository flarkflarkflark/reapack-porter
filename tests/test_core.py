from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from reapack_porter.core import (
    ConfigEncodingError,
    ImportVerificationError,
    IniFormatError,
    Remote,
    backup_path_for,
    decode_ini_bytes,
    import_remotes,
    merge_remotes,
    normalize_url,
    parse_remotes,
    read_ini_file,
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


def test_decode_ini_bytes_plain_utf8() -> None:
    decoded = decode_ini_bytes("[remotes]\nremote0=Café|https://example.com/a|1|0\nsize=1\n".encode("utf-8"))
    assert decoded.encoding == "utf-8"
    assert "Café" in decoded.text


def test_decode_ini_bytes_utf8_bom_strips_bom_and_reports_encoding() -> None:
    data = "[remotes]\nremote0=One|https://example.com/a|1|0\nsize=1\n".encode("utf-8-sig")
    decoded = decode_ini_bytes(data)
    assert decoded.encoding == "utf-8-sig"
    assert decoded.text.startswith("[remotes]")
    assert "﻿" not in decoded.text


def test_decode_ini_bytes_cp1252_supports_reported_names() -> None:
    text = (
        "[remotes]\r\n"
        "remote0=Müller|https://example.com/mueller|1|1\r\n"
        "remote1=Café|https://example.com/cafe|1|0\r\n"
        "remote2=Björk|https://example.com/bjork|1|0\r\n"
        "size=3\r\n"
    )
    decoded = decode_ini_bytes(text.encode("cp1252"))
    assert decoded.encoding == "cp1252"
    assert decoded.text == text


def test_decode_ini_bytes_reports_source_byte_0xfc_reproduces_reported_bug() -> None:
    data = "Müller".encode("cp1252")
    assert b"\xfc" in data
    with pytest.raises(UnicodeDecodeError):
        data.decode("utf-8")
    decoded = decode_ini_bytes(data)
    assert decoded.text == "Müller"


def test_decode_ini_bytes_raises_config_encoding_error_for_undecodable_bytes() -> None:
    with pytest.raises(ConfigEncodingError):
        decode_ini_bytes(b"[remotes]\n\x81\nsize=0\n", path="reapack.ini")


def test_read_ini_file_reads_cp1252_from_disk(tmp_path: Path) -> None:
    target = tmp_path / "reapack.ini"
    target.write_bytes("[remotes]\nremote0=Müller|https://example.com/a|1|0\nsize=1\n".encode("cp1252"))
    decoded = read_ini_file(target)
    assert decoded.encoding == "cp1252"
    assert "Müller" in decoded.text


def test_import_remotes_preserves_cp1252_encoding_backup_and_other_sections(tmp_path: Path) -> None:
    target = tmp_path / "reapack.ini"
    original_text = (
        "[other]\r\n"
        "display_name=Müller\r\n"
        "custom=Café\r\n"
        "\r\n"
        "[remotes]\r\n"
        "remote0=Björk|https://example.com/bjork|1|0\r\n"
        "size=1\r\n"
    )
    original_bytes = original_text.encode("cp1252")
    target.write_bytes(original_bytes)

    backup, added, skipped, total = import_remotes(
        target,
        [Remote("Müller Repo", "https://example.com/mueller", "1", "1")],
        now=datetime(2026, 7, 12, 10, 0, 0),
    )

    assert backup.read_bytes() == original_bytes
    assert added == 1
    assert skipped == 0
    assert total == 2

    written_bytes = target.read_bytes()
    written_text = written_bytes.decode("cp1252")
    assert "[other]\r\ndisplay_name=Müller\r\ncustom=Café\r\n\r\n[remotes]" in written_text
    assert "remote0=Björk|https://example.com/bjork|1|0" in written_text
    assert "remote1=Müller Repo|https://example.com/mueller|1|1" in written_text
    assert "ü".encode("cp1252") in written_bytes
    assert not list(tmp_path.glob("reapack.ini.tmp.*"))


def test_import_remotes_preserves_utf8_bom_without_duplicating(tmp_path: Path) -> None:
    target = tmp_path / "reapack.ini"
    original_text = "[general]\nversion=4\n\n[remotes]\nremote0=One|https://example.com/one|1|0\nsize=1\n"
    original_bytes = original_text.encode("utf-8-sig")
    target.write_bytes(original_bytes)

    backup, added, skipped, total = import_remotes(
        target,
        [Remote("Two", "https://example.com/two", "1", "1")],
        now=datetime(2026, 7, 12, 10, 0, 0),
    )

    assert backup.read_bytes() == original_bytes
    written = target.read_bytes()
    assert written.startswith(b"\xef\xbb\xbf")
    assert written.count(b"\xef\xbb\xbf") == 1
    assert "remote1=Two|https://example.com/two|1|1" in written.decode("utf-8-sig")


def test_import_remotes_preserves_crlf_newline(tmp_path: Path) -> None:
    target = tmp_path / "reapack.ini"
    target.write_bytes(
        b"[general]\r\nversion=4\r\n\r\n[remotes]\r\nremote0=One|https://example.com/one|1|0\r\nsize=1\r\n"
    )
    import_remotes(
        target,
        [Remote("Two", "https://example.com/two", "1", "1")],
        now=datetime(2026, 7, 12, 10, 0, 0),
    )
    written_text = target.read_bytes().decode("utf-8")
    assert written_text.count("\n") == written_text.count("\r\n")
    assert "remote1=Two|https://example.com/two|1|1\r\n" in written_text


def test_import_remotes_preserves_lf_newline(tmp_path: Path) -> None:
    target = tmp_path / "reapack.ini"
    target.write_bytes(
        b"[general]\nversion=4\n\n[remotes]\nremote0=One|https://example.com/one|1|0\nsize=1\n"
    )
    import_remotes(
        target,
        [Remote("Two", "https://example.com/two", "1", "1")],
        now=datetime(2026, 7, 12, 10, 0, 0),
    )
    written_bytes = target.read_bytes()
    assert b"\r\n" not in written_bytes
    assert b"remote1=Two|https://example.com/two|1|1\n" in written_bytes


def test_import_remotes_raises_config_encoding_error_and_makes_no_backup(tmp_path: Path) -> None:
    target = tmp_path / "reapack.ini"
    target.write_bytes(b"[general]\nversion=4\n\x81\n[remotes]\nsize=0\n")

    with pytest.raises(ConfigEncodingError):
        import_remotes(
            target,
            [Remote("Repo", "https://example.com/repo", "1", "0")],
            now=datetime(2026, 7, 12, 10, 0, 0),
        )

    assert not list(tmp_path.glob("reapack.ini.bak.*"))
    assert not list(tmp_path.glob("reapack.ini.tmp.*"))


@pytest.mark.parametrize("unrepresentable_name", ["日本語 Repository", "🎵 Music Repository"])
def test_import_remotes_cp1252_target_rejects_unrepresentable_import_cleanly(
    tmp_path: Path, unrepresentable_name: str
) -> None:
    target = tmp_path / "reapack.ini"
    original_text = (
        "[general]\r\nversion=4\r\n\r\n[remotes]\r\n"
        "remote0=Existing|https://example.com/existing|1|1\r\n"
        "size=1\r\n\r\n[other]\r\ndisplay_name=Müller\r\n"
    )
    original_bytes = original_text.encode("cp1252")
    target.write_bytes(original_bytes)

    with pytest.raises(ConfigEncodingError) as excinfo:
        import_remotes(
            target,
            [Remote(unrepresentable_name, "https://example.com/unicode", "1", "0")],
            now=datetime(2026, 8, 20, 12, 0, 0),
        )

    assert "cp1252" in str(excinfo.value)
    assert target.read_bytes() == original_bytes
    assert not list(tmp_path.glob("reapack.ini.bak.*"))
    assert not list(tmp_path.glob("reapack.ini.tmp.*"))


def test_import_remotes_backup_creation_failure_leaves_target_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reapack_porter.core import BackupError

    target = tmp_path / "reapack.ini"
    original_bytes = b"[general]\nversion=4\n\n[remotes]\nremote0=One|https://example.com/one|1|0\nsize=1\n"
    target.write_bytes(original_bytes)

    def broken_copyfile(src, dst):
        raise OSError("simulated disk failure during backup")

    monkeypatch.setattr("reapack_porter.core.shutil.copyfile", broken_copyfile)

    with pytest.raises(BackupError):
        import_remotes(
            target,
            [Remote("Two", "https://example.com/two", "1", "1")],
            now=datetime(2026, 7, 12, 10, 0, 0),
        )

    assert target.read_bytes() == original_bytes
    assert not list(tmp_path.glob("reapack.ini.tmp.*"))
