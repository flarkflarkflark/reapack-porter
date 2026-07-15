from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import platform as platform_module
import plistlib
import shutil
import subprocess
import sys
import tempfile


EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_ERROR = 5

PLATFORMS = ("linux", "windows", "macos")
ARCHES = ("x86_64", "arm64")


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class FrozenOutputs:
    gui: Path
    cli: Path


def normalize_arch(value: str | None = None) -> str:
    arch = (value or platform_module.machine()).lower()
    if arch in {"x86_64", "amd64"}:
        return "x86_64"
    if arch in {"arm64", "aarch64"}:
        return "arm64"
    return arch


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def clean_env(extra_home: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if extra_home is not None:
        env["HOME"] = str(extra_home / "home")
        env["USERPROFILE"] = str(extra_home / "profile")
        env["XDG_CONFIG_HOME"] = str(extra_home / "xdg")
        for key in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME"):
            Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


def expected_outputs(platform: str, dist_dir: str | Path) -> FrozenOutputs:
    dist = Path(dist_dir)
    if platform == "linux":
        return FrozenOutputs(gui=dist / "ReaPack-Porter" / "ReaPack-Porter", cli=dist / "reapack-porter-cli")
    if platform == "windows":
        return FrozenOutputs(gui=dist / "ReaPack-Porter" / "ReaPack-Porter.exe", cli=dist / "reapack-porter-cli.exe")
    if platform == "macos":
        app = dist / "ReaPack Porter.app"
        plist = app / "Contents" / "Info.plist"
        executable = "ReaPack-Porter"
        if plist.is_file():
            with plist.open("rb") as handle:
                executable = str(plistlib.load(handle).get("CFBundleExecutable") or executable)
        return FrozenOutputs(gui=app / "Contents" / "MacOS" / executable, cli=dist / "reapack-porter-cli")
    raise VerificationError(f"Unsupported platform: {platform}")


def check_architecture(expected: str) -> None:
    actual = normalize_arch()
    if actual != expected:
        raise VerificationError(f"Architecture mismatch: expected {expected}, got {actual}")


def check_executable(path: Path) -> None:
    if not path.is_file():
        raise VerificationError(f"Missing executable: {path}")
    if os.name != "nt" and not os.access(path, os.X_OK):
        raise VerificationError(f"File is not executable: {path}")


def run_command(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    clean = clean_env() if env is None else dict(env)
    clean.pop("PYTHONPATH", None)
    return subprocess.run(args, cwd=cwd, env=clean, shell=False, text=True, capture_output=True, timeout=timeout)


def require_success(args: list[str], *, env: dict[str, str] | None = None, timeout: int = 30) -> None:
    result = run_command(args, env=env, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise VerificationError(f"Command failed ({result.returncode}): {' '.join(args)}\n{detail}")


def run_cli_smoke(cli: Path, *, env: dict[str, str]) -> None:
    require_success([str(cli), "--help"], env=env)
    require_success([str(cli), "export", "--help"], env=env)
    require_success([str(cli), "import", "--help"], env=env)


def run_frozen_cli_e2e(cli: Path, *, env: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory(prefix="reapack-porter-cli-smoke-") as temp_name:
        temp = Path(temp_name)
        source = _source_ini(temp / "source.ini")
        target = _target_ini(temp / "target.ini")
        before = target.read_bytes()
        out_dir = temp / "exports with spaces"
        zip_dir = temp / "zips"

        require_success([str(cli), "export", "--source", str(source), "--out", str(out_dir)], env=env)
        require_success(
            [str(cli), "export", "--source", str(source), "--out", str(zip_dir), "--zip", "--keep-folder"],
            env=env,
        )
        zip_paths = sorted(zip_dir.glob("*.zip"))
        if len(zip_paths) != 1:
            raise VerificationError("Frozen CLI ZIP export did not create exactly one ZIP")
        require_success([str(cli), "import", "--bundle", str(zip_paths[0]), "--target", str(target), "--dry-run"], env=env)
        if target.read_bytes() != before or list(temp.glob("target.ini.bak.*")):
            raise VerificationError("Frozen CLI dry-run import wrote target or created a backup")


def _source_ini(path: Path) -> Path:
    path.write_text(
        "[general]\nversion=4\n\n"
        "[remotes]\n"
        "remote0=Alpha Unicode|https://example.com/repository-\u00e9/index.xml|1|1\n"
        "remote1=Bob's Tools|https://example.com/bobs-tools/|1|0\n"
        "size=2\n",
        encoding="utf-8",
    )
    return path


def _target_ini(path: Path) -> Path:
    path.write_text(
        "[general]\nversion=4\n\n"
        "[remotes]\n"
        "remote0=Existing|https://example.com/bobs-tools|1|1\n"
        "size=1\n\n"
        "[other]\nvalue=preserve-me\n",
        encoding="utf-8",
    )
    return path


def run_operations_e2e(platform: str) -> None:
    src_dir = repo_root() / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from reapack_porter.operations import DEFAULT_DEPS, OperationDeps, export_repositories, import_repositories, preview_import

    with tempfile.TemporaryDirectory(prefix="reapack-porter-smoke-") as temp_name:
        temp = Path(temp_name)
        source = _source_ini(temp / "source.ini")
        target = _target_ini(temp / "target.ini")
        deps = OperationDeps(
            **{
                **DEFAULT_DEPS.__dict__,
                "is_reaper_running": lambda **kwargs: False,
                "now": lambda: datetime(2026, 7, 15, 12, 0, 0),
            }
        )
        folder_result = export_repositories(
            source=source,
            output_dir=temp / "exports",
            create_zip=False,
            keep_folder=False,
            deps=deps,
            env=clean_env(temp),
            cwd=temp,
            platform=platform,
        )
        zip_result = export_repositories(
            source=source,
            output_dir=temp / "zips",
            create_zip=True,
            keep_folder=True,
            deps=deps,
            env=clean_env(temp),
            cwd=temp,
            platform=platform,
        )
        before = target.read_bytes()
        plan = preview_import(bundle=zip_result.zip_path, target=target, deps=deps, env=clean_env(temp), platform=platform)
        if plan.added_count != 1 or plan.skipped_count != 1:
            raise VerificationError("Dry-run import plan did not report expected add/skip counts")
        if target.read_bytes() != before or list(temp.glob("target.ini.bak.*")):
            raise VerificationError("Dry-run import wrote target or created a backup")

        result = import_repositories(
            bundle=folder_result.bundle_path,
            target=target,
            deps=deps,
            env=clean_env(temp),
            platform=platform,
        )
        text = target.read_text(encoding="utf-8")
        if result.added_count != 1 or result.skipped_count != 1 or result.total_count != 2:
            raise VerificationError("Real import did not report expected add/skip/total counts")
        if "[other]" not in text or "value=preserve-me" not in text:
            raise VerificationError("Import did not preserve unrelated ini sections")
        if text.lower().count("https://example.com/bobs-tools") != 1:
            raise VerificationError("Import did not skip trailing-slash duplicate")
        if not result.backup_path.is_file():
            raise VerificationError("Real import did not create a backup")


def run_gui_smoke(platform: str, gui: Path, *, env: dict[str, str]) -> None:
    if platform == "linux":
        if shutil.which("xvfb-run") is None:
            raise VerificationError("xvfb-run is required for Linux GUI smoke")
        result = run_command(["xvfb-run", "-a", "timeout", "5s", str(gui)], env=env, timeout=15)
        if result.returncode not in {0, 124}:
            detail = (result.stderr or result.stdout).strip()
            raise VerificationError(f"Linux GUI smoke failed with exit code {result.returncode}: {detail}")
        return

    process = subprocess.Popen([str(gui)], env=env, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return
    stdout, stderr = process.communicate()
    if return_code != 0:
        raise VerificationError(f"GUI exited early with code {return_code}: {(stderr or stdout).strip()}")


def verify_frozen_build(*, platform: str, arch: str, dist_dir: str | Path, skip_gui_smoke: bool = False) -> None:
    check_architecture(arch)
    outputs = expected_outputs(platform, dist_dir)
    check_executable(outputs.gui)
    check_executable(outputs.cli)
    with tempfile.TemporaryDirectory(prefix="reapack-porter-frozen-home-") as temp_name:
        env = clean_env(Path(temp_name))
        run_cli_smoke(outputs.cli, env=env)
        run_frozen_cli_e2e(outputs.cli, env=env)
        run_operations_e2e(platform)
        if not skip_gui_smoke:
            run_gui_smoke(platform, outputs.gui, env=env)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify ReaPack Porter frozen build outputs.")
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--arch", choices=ARCHES, required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--skip-gui-smoke", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        verify_frozen_build(
            platform=args.platform,
            arch=args.arch,
            dist_dir=args.dist_dir,
            skip_gui_smoke=args.skip_gui_smoke,
        )
    except Exception as exc:
        if args.debug:
            raise
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    print("Frozen build verification OK")
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
