from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tarfile
import zipfile

import pytest

from tools import package_artifacts


def _make_dist(tmp_path: Path, platform: str) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    if platform == "macos":
        gui = dist / "ReaPack Porter.app" / "Contents" / "MacOS"
        gui.mkdir(parents=True)
        exe = gui / "ReaPack-Porter"
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        exe.chmod(0o755)
        cli = dist / "reapack-porter-cli"
    elif platform == "windows":
        gui = dist / "ReaPack-Porter"
        gui.mkdir()
        (gui / "ReaPack-Porter.exe").write_text("gui", encoding="utf-8")
        cli = dist / "reapack-porter-cli.exe"
    else:
        gui = dist / "ReaPack-Porter"
        gui.mkdir()
        exe = gui / "ReaPack-Porter"
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        exe.chmod(0o755)
        cli = dist / "reapack-porter-cli"
    cli.write_text("#!/bin/sh\n", encoding="utf-8")
    cli.chmod(0o755)
    return dist


def test_artifact_names_include_project_version() -> None:
    expected = {
        ("linux", "x86_64"): "ReaPack-Porter-0.1.0-linux-x86_64.tar.gz",
        ("windows", "x86_64"): "ReaPack-Porter-0.1.0-windows-x86_64.zip",
        ("macos", "x86_64"): "ReaPack-Porter-0.1.0-macos-x86_64.zip",
        ("macos", "arm64"): "ReaPack-Porter-0.1.0-macos-arm64.zip",
    }
    for (platform, arch), filename in expected.items():
        paths = package_artifacts.artifact_paths(platform=platform, arch=arch, output_dir="release")
        assert paths.archive == Path("release") / filename
        assert paths.checksum == Path("release") / f"{filename}.sha256"


def test_platform_and_architecture_normalization() -> None:
    assert package_artifacts.normalize_platform("linux") == "linux"
    assert package_artifacts.normalize_platform("win32") == "windows"
    assert package_artifacts.normalize_platform("darwin") == "macos"
    assert package_artifacts.normalize_arch("AMD64") == "x86_64"
    assert package_artifacts.normalize_arch("aarch64") == "arm64"


def test_linux_tar_contains_top_folder_and_preserves_executable_bit(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path, "linux")
    paths = package_artifacts.create_artifact(
        platform="linux",
        arch="x86_64",
        dist_dir=dist,
        output_dir=tmp_path / "release",
    )
    with tarfile.open(paths.archive, "r:gz") as tar:
        names = tar.getnames()
        cli = tar.getmember(f"{paths.top_dir}/reapack-porter-cli")
    assert f"{paths.top_dir}/ReaPack-Porter/ReaPack-Porter" in names
    assert cli.mode & 0o111
    assert paths.checksum.read_text(encoding="utf-8").endswith(f"  {paths.archive.name}\n")


def test_windows_zip_contains_expected_members(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path, "windows")
    paths = package_artifacts.create_artifact(
        platform="windows",
        arch="x86_64",
        dist_dir=dist,
        output_dir=tmp_path / "release",
    )
    with zipfile.ZipFile(paths.archive) as zf:
        names = zf.namelist()
    assert f"{paths.top_dir}/ReaPack-Porter/ReaPack-Porter.exe" in names
    assert f"{paths.top_dir}/reapack-porter-cli.exe" in names
    package_artifacts.verify_artifact(
        archive=paths.archive,
        checksum=paths.checksum,
        platform="windows",
        arch="x86_64",
    )


def test_macos_packaging_uses_ditto_without_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dist = _make_dist(tmp_path, "macos")
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        archive = Path(args[-1])
        source = Path(args[-2])
        with zipfile.ZipFile(archive, "w") as zf:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    zf.write(path, source.name + "/" + path.relative_to(source).as_posix())
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(package_artifacts.subprocess, "run", fake_run)
    paths = package_artifacts.create_artifact(
        platform="macos",
        arch="arm64",
        dist_dir=dist,
        output_dir=tmp_path / "release",
    )
    assert captured["args"][:5] == ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent"]
    assert captured["kwargs"]["shell"] is False
    package_artifacts.verify_artifact(archive=paths.archive, checksum=paths.checksum, platform="macos", arch="arm64")


def test_checksum_tampering_is_rejected(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path, "linux")
    paths = package_artifacts.create_artifact(platform="linux", arch="x86_64", dist_dir=dist, output_dir=tmp_path / "release")
    paths.checksum.write_text("bad  name\n", encoding="utf-8")
    with pytest.raises(package_artifacts.PackageError, match="Checksum mismatch"):
        package_artifacts.verify_artifact(archive=paths.archive, checksum=paths.checksum, platform="linux", arch="x86_64")


def test_existing_output_requires_force(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path, "linux")
    package_artifacts.create_artifact(platform="linux", arch="x86_64", dist_dir=dist, output_dir=tmp_path / "release")
    with pytest.raises(package_artifacts.PackageError, match="without --force"):
        package_artifacts.create_artifact(platform="linux", arch="x86_64", dist_dir=dist, output_dir=tmp_path / "release")


def test_force_overwrites_only_intended_outputs(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path, "linux")
    release = tmp_path / "release"
    other = release / "keep-me.txt"
    release.mkdir()
    other.write_text("keep", encoding="utf-8")
    first = package_artifacts.create_artifact(platform="linux", arch="x86_64", dist_dir=dist, output_dir=release)
    first.archive.write_text("replace", encoding="utf-8")
    package_artifacts.create_artifact(platform="linux", arch="x86_64", dist_dir=dist, output_dir=release, force=True)
    assert other.read_text(encoding="utf-8") == "keep"
    assert first.checksum.is_file()


def test_forbidden_files_are_rejected_and_staging_is_cleaned(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path, "linux")
    (dist / "ReaPack-Porter" / "settings.json").write_text("no", encoding="utf-8")
    release = tmp_path / "release"
    release.mkdir()
    with pytest.raises(package_artifacts.PackageError, match="Forbidden"):
        package_artifacts.create_artifact(platform="linux", arch="x86_64", dist_dir=dist, output_dir=release)
    assert not list(release.glob(".package-*"))


def test_paths_with_spaces_apostrophe_and_unicode_are_packaged(tmp_path: Path) -> None:
    dist_root = tmp_path / "dist with spaces and \u00e9"
    dist_root.mkdir()
    dist = _make_dist(dist_root, "linux")
    (dist / "ReaPack-Porter" / "Bob's tool \u00e9.txt").write_text("ok", encoding="utf-8")
    paths = package_artifacts.create_artifact(
        platform="linux",
        arch="x86_64",
        dist_dir=dist,
        output_dir=tmp_path / "release with spaces",
    )
    package_artifacts.verify_artifact(archive=paths.archive, checksum=paths.checksum, platform="linux", arch="x86_64")


def test_missing_gui_or_cli_is_rejected(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path, "linux")
    (dist / "reapack-porter-cli").unlink()
    with pytest.raises(package_artifacts.PackageError, match="Missing frozen CLI"):
        package_artifacts.create_artifact(platform="linux", arch="x86_64", dist_dir=dist, output_dir=tmp_path / "release")


def test_paths_command_writes_github_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert package_artifacts.main(["paths", "--platform", "linux", "--arch", "x86_64", "--output-dir", str(tmp_path / "release")]) == 0
    text = output.read_text(encoding="utf-8")
    assert "archive=" in text
    assert "checksum=" in text
