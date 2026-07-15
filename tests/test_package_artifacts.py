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


def test_expected_release_artifacts_are_exact_four_platform_archives() -> None:
    names = [paths.archive.name for paths in package_artifacts.expected_release_artifacts(output_dir="release")]
    assert names == [
        "ReaPack-Porter-0.1.0-linux-x86_64.tar.gz",
        "ReaPack-Porter-0.1.0-windows-x86_64.zip",
        "ReaPack-Porter-0.1.0-macos-x86_64.zip",
        "ReaPack-Porter-0.1.0-macos-arm64.zip",
    ]


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


def _write_release_archive(path: Path, platform: str, arch: str) -> None:
    top = f"ReaPack-Porter-0.1.0-{platform}-{arch}"
    if platform == "linux":
        with tarfile.open(path, "w:gz") as tar:
            for name, data in {
                f"{top}/ReaPack-Porter/ReaPack-Porter": b"gui",
                f"{top}/reapack-porter-cli": b"cli",
            }.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o755
                import io

                tar.addfile(info, io.BytesIO(data))
        return
    with zipfile.ZipFile(path, "w") as zf:
        if platform == "windows":
            zf.writestr(f"{top}/ReaPack-Porter/ReaPack-Porter.exe", "gui")
            zf.writestr(f"{top}/reapack-porter-cli.exe", "cli")
        else:
            zf.writestr(f"{top}/ReaPack Porter.app/Contents/MacOS/ReaPack-Porter", "gui")
            zf.writestr(f"{top}/reapack-porter-cli", "cli")


def _make_release_set(root: Path, *, nested: bool = False) -> dict[str, bytes]:
    before: dict[str, bytes] = {}
    for paths in package_artifacts.expected_release_artifacts(output_dir=root):
        parts = paths.top_dir.rsplit("-", 2)
        platform, arch = parts[1], parts[2]
        target_dir = root / f"artifact {platform} {arch}" if nested else root
        target_dir.mkdir(parents=True, exist_ok=True)
        archive = target_dir / paths.archive.name
        _write_release_archive(archive, platform, arch)
        checksum = package_artifacts.write_checksum(archive)
        before[archive.name] = archive.read_bytes()
        before[checksum.name] = checksum.read_bytes()
    return before


def test_verify_release_set_finds_recursive_artifacts_and_writes_manifest(tmp_path: Path) -> None:
    before = _make_release_set(tmp_path, nested=True)
    manifest = tmp_path / "SHA256SUMS.txt"
    package_artifacts.verify_release_set(input_dir=tmp_path, manifest=manifest)
    lines = manifest.read_text(encoding="utf-8").splitlines()
    filenames = [line.split("  ", 1)[1] for line in lines]
    assert filenames == sorted(filenames)
    assert len(lines) == 4
    for line in lines:
        digest, filename = line.split("  ", 1)
        assert len(digest) == 64
        assert digest == digest.lower()
        assert Path(filename).name == filename
        assert "  " in line
        assert "/" not in filename
    assert manifest.read_bytes().endswith(b"\n")
    for path in tmp_path.rglob("*"):
        if path.is_file() and path.name in before:
            assert path.read_bytes() == before[path.name]


def test_verify_release_set_calls_platform_verifier_for_each_artifact(tmp_path: Path) -> None:
    _make_release_set(tmp_path)
    calls: list[tuple[str, str, str]] = []

    def fake_verifier(*, archive: Path, checksum: Path, platform: str, arch: str) -> None:
        calls.append((archive.name, platform, arch))
        assert checksum.name == f"{archive.name}.sha256"

    package_artifacts.verify_release_set(input_dir=tmp_path, manifest=tmp_path / "SHA256SUMS.txt", verifier=fake_verifier)
    assert calls == [
        ("ReaPack-Porter-0.1.0-linux-x86_64.tar.gz", "linux", "x86_64"),
        ("ReaPack-Porter-0.1.0-macos-arm64.zip", "macos", "arm64"),
        ("ReaPack-Porter-0.1.0-macos-x86_64.zip", "macos", "x86_64"),
        ("ReaPack-Porter-0.1.0-windows-x86_64.zip", "windows", "x86_64"),
    ]


def test_verify_release_set_rejects_missing_archive_and_sidecar(tmp_path: Path) -> None:
    _make_release_set(tmp_path)
    (tmp_path / "ReaPack-Porter-0.1.0-linux-x86_64.tar.gz").unlink()
    (tmp_path / "ReaPack-Porter-0.1.0-windows-x86_64.zip.sha256").unlink()
    with pytest.raises(package_artifacts.PackageError) as excinfo:
        package_artifacts.verify_release_set(input_dir=tmp_path, manifest=tmp_path / "SHA256SUMS.txt")
    message = str(excinfo.value)
    assert "missing archives: ReaPack-Porter-0.1.0-linux-x86_64.tar.gz" in message
    assert "missing sidecars: ReaPack-Porter-0.1.0-windows-x86_64.zip.sha256" in message


def test_verify_release_set_rejects_checksum_mismatch(tmp_path: Path) -> None:
    _make_release_set(tmp_path)
    (tmp_path / "ReaPack-Porter-0.1.0-linux-x86_64.tar.gz.sha256").write_text("0" * 64 + "  ReaPack-Porter-0.1.0-linux-x86_64.tar.gz\n", encoding="utf-8")
    with pytest.raises(package_artifacts.PackageError, match="Checksum mismatch"):
        package_artifacts.verify_release_set(input_dir=tmp_path, manifest=tmp_path / "SHA256SUMS.txt")


def test_verify_release_set_rejects_duplicate_basename(tmp_path: Path) -> None:
    _make_release_set(tmp_path)
    duplicate_dir = tmp_path / "duplicate"
    duplicate_dir.mkdir()
    source = tmp_path / "ReaPack-Porter-0.1.0-linux-x86_64.tar.gz"
    (duplicate_dir / source.name).write_bytes(source.read_bytes())
    with pytest.raises(package_artifacts.PackageError, match="Duplicate archive basename"):
        package_artifacts.verify_release_set(input_dir=tmp_path, manifest=tmp_path / "SHA256SUMS.txt")


def test_verify_release_set_rejects_unexpected_archive_and_sidecar(tmp_path: Path) -> None:
    _make_release_set(tmp_path)
    extra_archive = tmp_path / "ReaPack-Porter-0.1.0-freebsd-x86_64.zip"
    extra_archive.write_text("extra", encoding="utf-8")
    (tmp_path / f"{extra_archive.name}.sha256").write_text("0" * 64 + f"  {extra_archive.name}\n", encoding="utf-8")
    with pytest.raises(package_artifacts.PackageError) as excinfo:
        package_artifacts.verify_release_set(input_dir=tmp_path, manifest=tmp_path / "SHA256SUMS.txt")
    assert "unexpected archives: ReaPack-Porter-0.1.0-freebsd-x86_64.zip" in str(excinfo.value)
    assert "unexpected sidecars: ReaPack-Porter-0.1.0-freebsd-x86_64.zip.sha256" in str(excinfo.value)


def test_verify_release_set_refuses_existing_manifest_without_force(tmp_path: Path) -> None:
    _make_release_set(tmp_path)
    manifest = tmp_path / "SHA256SUMS.txt"
    manifest.write_text("keep\n", encoding="utf-8")
    with pytest.raises(package_artifacts.PackageError, match="without --force"):
        package_artifacts.verify_release_set(input_dir=tmp_path, manifest=manifest)
    assert manifest.read_text(encoding="utf-8") == "keep\n"


def test_verify_release_set_force_replaces_only_manifest(tmp_path: Path) -> None:
    before = _make_release_set(tmp_path)
    manifest = tmp_path / "SHA256SUMS.txt"
    manifest.write_text("replace\n", encoding="utf-8")
    package_artifacts.verify_release_set(input_dir=tmp_path, manifest=manifest, force=True)
    assert len(manifest.read_text(encoding="utf-8").splitlines()) == 4
    for path in tmp_path.iterdir():
        if path.is_file() and path.name in before:
            assert path.read_bytes() == before[path.name]


def test_verify_release_set_atomic_failure_leaves_no_half_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _make_release_set(tmp_path)
    manifest = tmp_path / "SHA256SUMS.txt"

    def fail_replace(src: Path, dst: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(package_artifacts.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        package_artifacts.verify_release_set(input_dir=tmp_path, manifest=manifest)
    assert not manifest.exists()
    assert not list(tmp_path.glob(".SHA256SUMS.txt.tmp"))


def test_verify_set_cli_help_and_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_release_set(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        package_artifacts.main(["verify-set", "--help"])
    assert excinfo.value.code == 0
    assert package_artifacts.main(["verify-set", "--input-dir", str(tmp_path), "--manifest", str(tmp_path / "SHA256SUMS.txt")]) == 0
    assert "Release set verification OK" in capsys.readouterr().out
