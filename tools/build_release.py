from __future__ import annotations

import argparse
import platform as platform_module
from pathlib import Path
import shutil
import subprocess
import sys


EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_BUILD_ERROR = 5

PYINSTALLER_MISSING_MESSAGE = "PyInstaller is not installed. Install the build extra in an isolated environment."


class BuildError(RuntimeError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def normalize_platform(value: str | None = None) -> str:
    name = (value or sys.platform).lower()
    if name.startswith("linux"):
        return "linux"
    if name.startswith("win") or name in {"cygwin", "msys"}:
        return "windows"
    if name == "darwin":
        return "macos"
    return name


def normalize_arch(value: str | None = None) -> str:
    arch = (value or platform_module.machine()).lower()
    if arch in {"x86_64", "amd64"}:
        return "x86_64"
    if arch in {"arm64", "aarch64"}:
        return "arm64"
    return arch


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ReaPack Porter frozen release targets.")
    parser.add_argument("--target", choices=("gui", "cli", "all"), required=True, help="release target to build")
    parser.add_argument("--clean", action="store_true", help="remove generated build output before building")
    parser.add_argument("--dist-dir", type=Path, default=None, help="PyInstaller dist directory")
    parser.add_argument("--work-dir", type=Path, default=None, help="PyInstaller work directory")
    parser.add_argument("--log-level", default="INFO", help="PyInstaller log level")
    parser.add_argument("--debug", action="store_true", help="show tracebacks for build errors")
    return parser.parse_args(argv)


def expand_targets(target: str) -> tuple[str, ...]:
    if target == "all":
        return ("gui", "cli")
    if target in {"gui", "cli"}:
        return (target,)
    raise BuildError(f"Unknown target: {target}")


def spec_for_target(target: str, root: Path) -> Path:
    specs = {
        "gui": root / "tools" / "pyinstaller" / "reapack_porter_gui.spec",
        "cli": root / "tools" / "pyinstaller" / "reapack_porter_cli.spec",
    }
    try:
        return specs[target]
    except KeyError as exc:
        raise BuildError(f"Unknown target: {target}") from exc


def ensure_python_version() -> None:
    if sys.version_info < (3, 10):
        raise BuildError("Python 3.10 or newer is required.")


def check_tkinter() -> None:
    try:
        __import__("tkinter")
    except Exception as exc:
        raise BuildError(f"Tkinter is not available: {exc}") from exc


def _ensure_clean_target(path: Path) -> None:
    allowed_names = {"dist", ".pyinstaller-work", "release"}
    if path.name not in allowed_names:
        raise BuildError(f"Refusing to clean unexpected path: {path}")


def clean_outputs(dist_dir: Path, work_dir: Path) -> None:
    for path in (dist_dir, work_dir):
        _ensure_clean_target(path)
        if path.exists():
            shutil.rmtree(path)


def run_pyinstaller(
    spec_path: Path,
    *,
    repo_root: Path,
    dist_dir: Path,
    work_dir: Path,
    log_level: str,
) -> None:
    if not spec_path.is_file():
        raise BuildError(f"Missing PyInstaller spec: {spec_path}")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--log-level",
        log_level,
        str(spec_path),
    ]
    result = subprocess.run(command, cwd=repo_root, shell=False, text=True, capture_output=True)
    if result.returncode == 0:
        return
    stderr = result.stderr or ""
    if "No module named PyInstaller" in stderr:
        raise BuildError(PYINSTALLER_MISSING_MESSAGE)
    raise BuildError(f"PyInstaller failed for {spec_path.name} with exit code {result.returncode}.")


def build_target(
    target: str,
    *,
    repo_root: Path,
    dist_dir: Path,
    work_dir: Path,
    clean: bool,
    debug: bool,
    log_level: str = "INFO",
) -> None:
    del debug
    ensure_python_version()
    if clean:
        clean_outputs(dist_dir, work_dir)
    if target == "gui":
        check_tkinter()
    run_pyinstaller(
        spec_for_target(target, repo_root),
        repo_root=repo_root,
        dist_dir=dist_dir,
        work_dir=work_dir,
        log_level=log_level,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    dist_dir = args.dist_dir or root / "dist"
    work_dir = args.work_dir or root / ".pyinstaller-work"

    try:
        ensure_python_version()
        print(f"Platform: {normalize_platform()} {normalize_arch()}")
        for target in expand_targets(args.target):
            print(f"Building {target} target...")
            build_target(
                target,
                repo_root=root,
                dist_dir=dist_dir,
                work_dir=work_dir,
                clean=args.clean and target == expand_targets(args.target)[0],
                debug=args.debug,
                log_level=args.log_level,
            )
    except BuildError as exc:
        if args.debug:
            raise
        print(str(exc), file=sys.stderr)
        return EXIT_BUILD_ERROR
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
