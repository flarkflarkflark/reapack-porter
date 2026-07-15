from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile


EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_ERROR = 5

PRODUCT = "ReaPack-Porter"
FORBIDDEN_NAMES = {
    ".snapshots",
    "README.md",
    "reapack.ini",
    "reapack_porter.lua",
    "screenshots",
    "settings.json",
}
PLATFORMS = ("linux", "windows", "macos")
ARCHES = ("x86_64", "arm64")
RELEASE_TARGETS = (
    ("linux", "x86_64"),
    ("windows", "x86_64"),
    ("macos", "x86_64"),
    ("macos", "arm64"),
)


class PackageError(RuntimeError):
    pass


def _arg_error(message: str) -> argparse.ArgumentTypeError:
    return argparse.ArgumentTypeError(message)


@dataclass(frozen=True)
class ArtifactPaths:
    archive: Path
    checksum: Path
    top_dir: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_version(project_root: Path | None = None) -> str:
    root = project_root or repo_root()
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def normalize_platform(value: str) -> str:
    platform = value.lower()
    if platform.startswith("linux"):
        return "linux"
    if platform in {"windows", "win32", "cygwin", "msys"}:
        return "windows"
    if platform in {"macos", "darwin"}:
        return "macos"
    raise _arg_error(f"Unsupported platform: {value}")


def normalize_arch(value: str) -> str:
    arch = value.lower()
    if arch in {"x86_64", "amd64"}:
        return "x86_64"
    if arch in {"arm64", "aarch64"}:
        return "arm64"
    raise _arg_error(f"Unsupported architecture: {value}")


def archive_extension(platform: str) -> str:
    if platform == "linux":
        return "tar.gz"
    if platform in {"windows", "macos"}:
        return "zip"
    raise PackageError(f"Unsupported platform: {platform}")


def artifact_paths(
    *,
    platform: str,
    arch: str,
    output_dir: str | Path,
    version: str | None = None,
) -> ArtifactPaths:
    platform = normalize_platform(platform)
    arch = normalize_arch(arch)
    version = version or read_version()
    top_dir = f"{PRODUCT}-{version}-{platform}-{arch}"
    archive = Path(output_dir) / f"{top_dir}.{archive_extension(platform)}"
    return ArtifactPaths(archive=archive, checksum=Path(f"{archive}.sha256"), top_dir=top_dir)


def expected_release_artifacts(*, output_dir: str | Path, version: str | None = None) -> tuple[ArtifactPaths, ...]:
    return tuple(
        artifact_paths(platform=platform, arch=arch, output_dir=output_dir, version=version)
        for platform, arch in RELEASE_TARGETS
    )


def expected_members(platform: str, dist_dir: Path) -> tuple[Path, Path]:
    platform = normalize_platform(platform)
    if platform == "linux":
        return dist_dir / "ReaPack-Porter", dist_dir / "reapack-porter-cli"
    if platform == "windows":
        return dist_dir / "ReaPack-Porter", dist_dir / "reapack-porter-cli.exe"
    if platform == "macos":
        return dist_dir / "ReaPack Porter.app", dist_dir / "reapack-porter-cli"
    raise PackageError(f"Unsupported platform: {platform}")


def _check_forbidden(path: Path) -> None:
    for part in path.parts:
        if part in FORBIDDEN_NAMES:
            raise PackageError(f"Forbidden file in artifact input: {path}")
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"} and "screenshot" in path.name.lower():
        raise PackageError(f"Forbidden screenshot in artifact input: {path}")


def _copy_required_inputs(platform: str, dist_dir: Path, staging_top: Path) -> None:
    gui, cli = expected_members(platform, dist_dir)
    if not gui.exists():
        raise PackageError(f"Missing frozen GUI output: {gui}")
    if not cli.is_file():
        raise PackageError(f"Missing frozen CLI output: {cli}")

    _check_forbidden(gui)
    _check_forbidden(cli)
    for path in gui.rglob("*") if gui.is_dir() else [gui]:
        _check_forbidden(path)

    if gui.is_dir():
        shutil.copytree(gui, staging_top / gui.name, symlinks=True)
    else:
        shutil.copy2(gui, staging_top / gui.name)
    shutil.copy2(cli, staging_top / cli.name)


def _refuse_existing(paths: ArtifactPaths, *, force: bool) -> None:
    existing = [path for path in (paths.archive, paths.checksum) if path.exists()]
    if existing and not force:
        raise PackageError("Refusing to overwrite existing output without --force: " + ", ".join(str(path) for path in existing))
    if force:
        for path in existing:
            path.unlink()


def _tar_directory(source_dir: Path, archive: Path) -> None:
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name, recursive=True)


def _zip_directory(source_dir: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            rel = source_dir.name + "/" + path.relative_to(source_dir).as_posix()
            if path.is_dir():
                zf.writestr(rel.rstrip("/") + "/", b"")
                continue
            info = zipfile.ZipInfo.from_file(path, arcname=rel)
            with path.open("rb") as handle:
                zf.writestr(info, handle.read(), compress_type=zipfile.ZIP_DEFLATED)


def _ditto_directory(source_dir: Path, archive: Path) -> None:
    command = ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(source_dir), str(archive)]
    result = subprocess.run(command, shell=False, text=True, capture_output=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "ditto failed"
        raise PackageError(message)


def write_checksum(archive: Path) -> Path:
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = Path(f"{archive}.sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8", newline="\n")
    return checksum


def _is_archive_name(name: str) -> bool:
    return name.endswith(".tar.gz") or name.endswith(".zip")


def _is_sidecar_name(name: str) -> bool:
    return name.endswith(".sha256")


def _collect_unique_basenames(paths: list[Path], *, kind: str) -> dict[str, Path]:
    by_name: dict[str, Path] = {}
    duplicates: list[str] = []
    for path in paths:
        if path.name in by_name:
            duplicates.append(path.name)
            continue
        by_name[path.name] = path
    if duplicates:
        raise PackageError(f"Duplicate {kind} basename: {', '.join(sorted(set(duplicates)))}")
    return by_name


def _find_release_files(input_dir: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    if not input_dir.is_dir():
        raise PackageError(f"Input directory not found: {input_dir}")
    files = [path for path in input_dir.rglob("*") if path.is_file()]
    archives = _collect_unique_basenames([path for path in files if _is_archive_name(path.name)], kind="archive")
    sidecars = _collect_unique_basenames([path for path in files if _is_sidecar_name(path.name)], kind="sidecar")
    return archives, sidecars


def _read_sidecar(checksum: Path, archive: Path) -> str:
    expected = f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}"
    actual = checksum.read_text(encoding="utf-8").strip()
    if actual != expected:
        raise PackageError(f"Checksum mismatch: {checksum.name}")
    digest, separator, filename = actual.partition("  ")
    if not separator or filename != archive.name:
        raise PackageError(f"Invalid checksum sidecar format: {checksum.name}")
    if len(digest) != 64 or digest.lower() != digest or any(char not in "0123456789abcdef" for char in digest):
        raise PackageError(f"Invalid checksum digest: {checksum.name}")
    return digest


def _write_manifest_atomic(manifest: Path, lines: list[str], *, force: bool) -> None:
    if manifest.exists() and not force:
        raise PackageError(f"Refusing to overwrite existing manifest without --force: {manifest}")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    temp = manifest.with_name(f".{manifest.name}.tmp")
    try:
        temp.write_text("".join(lines), encoding="utf-8", newline="\n")
        os.replace(temp, manifest)
    except Exception:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


def verify_release_set(
    *,
    input_dir: str | Path,
    manifest: str | Path,
    force: bool = False,
    verifier: Callable[..., None] | None = None,
) -> Path:
    verifier = verifier or verify_artifact
    version = read_version()
    root = Path(input_dir)
    manifest_path = Path(manifest)
    expected = expected_release_artifacts(output_dir=root, version=version)
    expected_archives = {paths.archive.name: paths for paths in expected}
    expected_sidecars = {paths.checksum.name for paths in expected}
    archives, sidecars = _find_release_files(root)

    missing_archives = sorted(set(expected_archives) - set(archives))
    missing_sidecars = sorted(expected_sidecars - set(sidecars))
    unexpected_archives = sorted(set(archives) - set(expected_archives))
    unexpected_sidecars = sorted(set(sidecars) - expected_sidecars)
    errors = []
    if missing_archives:
        errors.append("missing archives: " + ", ".join(missing_archives))
    if missing_sidecars:
        errors.append("missing sidecars: " + ", ".join(missing_sidecars))
    if unexpected_archives:
        errors.append("unexpected archives: " + ", ".join(unexpected_archives))
    if unexpected_sidecars:
        errors.append("unexpected sidecars: " + ", ".join(unexpected_sidecars))
    if errors:
        raise PackageError("; ".join(errors))

    manifest_lines: list[str] = []
    for archive_name in sorted(expected_archives):
        paths = expected_archives[archive_name]
        archive = archives[archive_name]
        checksum = sidecars[f"{archive_name}.sha256"]
        verifier(archive=archive, checksum=checksum, platform=paths.top_dir.rsplit("-", 2)[-2], arch=paths.top_dir.rsplit("-", 1)[-1])
        digest = _read_sidecar(checksum, archive)
        manifest_lines.append(f"{digest}  {archive.name}\n")

    _write_manifest_atomic(manifest_path, manifest_lines, force=force)
    return manifest_path


def create_artifact(
    *,
    platform: str,
    arch: str,
    dist_dir: str | Path,
    output_dir: str | Path,
    force: bool = False,
) -> ArtifactPaths:
    platform = normalize_platform(platform)
    arch = normalize_arch(arch)
    paths = artifact_paths(platform=platform, arch=arch, output_dir=output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    _refuse_existing(paths, force=force)

    temp_parent = Path(output_dir)
    with tempfile.TemporaryDirectory(prefix=".package-", dir=temp_parent) as temp_name:
        staging_root = Path(temp_name)
        staging_top = staging_root / paths.top_dir
        staging_top.mkdir()
        _copy_required_inputs(platform, Path(dist_dir), staging_top)
        if platform == "linux":
            _tar_directory(staging_top, paths.archive)
        elif platform == "windows":
            _zip_directory(staging_top, paths.archive)
        elif platform == "macos":
            _ditto_directory(staging_top, paths.archive)
        else:
            raise PackageError(f"Unsupported platform: {platform}")

    write_checksum(paths.archive)
    verify_artifact(archive=paths.archive, checksum=paths.checksum, platform=platform, arch=arch)
    return paths


def _read_archive_names(path: Path) -> list[str]:
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as tar:
            return tar.getnames()
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            return zf.namelist()
    raise PackageError(f"Unsupported archive type: {path}")


def _expected_archive_entries(platform: str, top_dir: str) -> tuple[str, str]:
    platform = normalize_platform(platform)
    if platform == "linux":
        return f"{top_dir}/ReaPack-Porter", f"{top_dir}/reapack-porter-cli"
    if platform == "windows":
        return f"{top_dir}/ReaPack-Porter", f"{top_dir}/reapack-porter-cli.exe"
    if platform == "macos":
        return f"{top_dir}/ReaPack Porter.app", f"{top_dir}/reapack-porter-cli"
    raise PackageError(f"Unsupported platform: {platform}")


def verify_artifact(*, archive: str | Path, checksum: str | Path, platform: str, arch: str) -> None:
    platform = normalize_platform(platform)
    arch = normalize_arch(arch)
    archive_path = Path(archive)
    checksum_path = Path(checksum)
    if not archive_path.is_file():
        raise PackageError(f"Archive not found: {archive_path}")
    if not checksum_path.is_file():
        raise PackageError(f"Checksum not found: {checksum_path}")

    expected_line = f"{hashlib.sha256(archive_path.read_bytes()).hexdigest()}  {archive_path.name}"
    actual_line = checksum_path.read_text(encoding="utf-8").strip()
    if actual_line != expected_line:
        raise PackageError("Checksum mismatch")

    version = read_version()
    expected = artifact_paths(platform=platform, arch=arch, output_dir=archive_path.parent, version=version)
    if archive_path.name != expected.archive.name:
        raise PackageError(f"Unexpected archive name: {archive_path.name}")

    names = _read_archive_names(archive_path)
    if not names:
        raise PackageError("Archive is empty")
    top_parts = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
    if top_parts != {expected.top_dir}:
        raise PackageError(f"Archive must contain exactly one top-level folder: {expected.top_dir}")

    for name in names:
        parts = set(PurePosixPath(name).parts)
        if parts & FORBIDDEN_NAMES:
            raise PackageError(f"Forbidden file in archive: {name}")
        if PurePosixPath(name).suffix.lower() in {".png", ".jpg", ".jpeg"} and "screenshot" in PurePosixPath(name).name.lower():
            raise PackageError(f"Forbidden screenshot in archive: {name}")

    gui_entry, cli_entry = _expected_archive_entries(platform, expected.top_dir)
    if not any(name == gui_entry or name.startswith(gui_entry.rstrip("/") + "/") for name in names):
        raise PackageError(f"Archive is missing GUI output: {gui_entry}")
    if cli_entry not in names:
        raise PackageError(f"Archive is missing CLI output: {cli_entry}")


def _write_github_output(paths: ArtifactPaths) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    with Path(output_file).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"archive={paths.archive.as_posix()}\n")
        handle.write(f"checksum={paths.checksum.as_posix()}\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "verify-set":
        parser = argparse.ArgumentParser(description="Verify a complete ReaPack Porter release asset set.")
        parser.add_argument("command", choices=("verify-set",))
        parser.add_argument("--input-dir", type=Path, required=True)
        parser.add_argument("--manifest", type=Path, required=True)
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--debug", action="store_true")
        return parser.parse_args(args)
    if args and args[0] == "verify":
        parser = argparse.ArgumentParser(description="Verify a ReaPack Porter standalone artifact.")
        parser.add_argument("command", choices=("verify",))
        parser.add_argument("--archive", type=Path, required=True)
        parser.add_argument("--checksum", type=Path, required=True)
        parser.add_argument("--platform", type=normalize_platform, required=True)
        parser.add_argument("--arch", type=normalize_arch, required=True)
        parser.add_argument("--debug", action="store_true")
        return parser.parse_args(args)
    if args and args[0] == "paths":
        parser = argparse.ArgumentParser(description="Resolve expected ReaPack Porter artifact paths.")
        parser.add_argument("command", choices=("paths",))
        parser.add_argument("--platform", type=normalize_platform, required=True)
        parser.add_argument("--arch", type=normalize_arch, required=True)
        parser.add_argument("--output-dir", type=Path, required=True)
        parser.add_argument("--debug", action="store_true")
        return parser.parse_args(args)
    parser = argparse.ArgumentParser(description="Package ReaPack Porter frozen build outputs.")
    parser.add_argument("--platform", type=normalize_platform, required=True)
    parser.add_argument("--arch", type=normalize_arch, required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args(args)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if getattr(args, "command", None) == "verify":
            verify_artifact(archive=args.archive, checksum=args.checksum, platform=args.platform, arch=args.arch)
            print("Artifact verification OK")
            return EXIT_SUCCESS
        if getattr(args, "command", None) == "verify-set":
            manifest = verify_release_set(input_dir=args.input_dir, manifest=args.manifest, force=args.force)
            print(f"Release set verification OK: {manifest}")
            return EXIT_SUCCESS
        if getattr(args, "command", None) == "paths":
            paths = artifact_paths(platform=args.platform, arch=args.arch, output_dir=args.output_dir)
            _write_github_output(paths)
            print(paths.archive)
            print(paths.checksum)
            return EXIT_SUCCESS
        paths = create_artifact(
            platform=args.platform,
            arch=args.arch,
            dist_dir=args.dist_dir,
            output_dir=args.output_dir,
            force=args.force,
        )
        print(paths.archive)
        print(paths.checksum)
        return EXIT_SUCCESS
    except (PackageError, OSError) as exc:
        if getattr(args, "debug", False):
            raise
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
