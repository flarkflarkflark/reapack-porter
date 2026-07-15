from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import subprocess
from typing import Callable, Sequence


REAPER_NAMES = {"reaper", "reaper.exe"}


class ProcessDetectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    command: str | None = None


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _matches_reaper_name(name: str) -> bool:
    candidate = PurePosixPath(name.replace("\\", "/")).name.lower()
    return candidate in REAPER_NAMES


def _linux_process_info(pid_dir: Path) -> ProcessInfo | None:
    try:
        pid = int(pid_dir.name)
        comm = (pid_dir / "comm").read_text(encoding="utf-8").strip()
        cmdline_bytes = (pid_dir / "cmdline").read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError, ValueError):
        return None

    cmdline_parts = [part.decode("utf-8", errors="ignore") for part in cmdline_bytes.split(b"\0") if part]
    command = " ".join(cmdline_parts) if cmdline_parts else None

    if _matches_reaper_name(comm):
        return ProcessInfo(pid=pid, name=comm, command=command)
    if cmdline_parts:
        first = PurePosixPath(cmdline_parts[0].replace("\\", "/")).name.lower()
        if _matches_reaper_name(first):
            return ProcessInfo(pid=pid, name=comm, command=command)
        if first.startswith("wine"):
            for part in cmdline_parts[1:]:
                if _matches_reaper_name(part):
                    return ProcessInfo(pid=pid, name=comm, command=command)
    return None


def _find_linux_reaper_processes(proc_root: Path) -> list[ProcessInfo]:
    processes: list[ProcessInfo] = []
    try:
        entries = list(proc_root.iterdir())
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError) as exc:
        raise ProcessDetectionError(
            f"Could not determine whether REAPER is running: could not inspect {proc_root}."
        ) from exc

    for child in entries:
        if not child.name.isdigit():
            continue
        info = _linux_process_info(child)
        if info is not None:
            processes.append(info)
    return sorted(processes, key=lambda process: process.pid)


def _default_runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ProcessDetectionError(
            f"Could not determine whether REAPER is running: failed to launch {args[0]}."
        ) from exc


def _find_windows_reaper_processes(runner: Runner) -> list[ProcessInfo]:
    result = runner(["tasklist", "/fo", "csv", "/nh"])
    if result.returncode != 0:
        raise ProcessDetectionError(
            f"Could not determine whether REAPER is running: tasklist failed with exit code {result.returncode}."
        )

    import csv
    from io import StringIO

    processes: list[ProcessInfo] = []
    reader = csv.reader(StringIO(result.stdout))
    for row in reader:
        if len(row) < 2:
            continue
        name = row[0].strip()
        pid_text = row[1].strip()
        if not _matches_reaper_name(name):
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            raise ProcessDetectionError(f"Could not parse tasklist PID value: {pid_text!r}")
        processes.append(ProcessInfo(pid=pid, name=name, command=None))
    return sorted(processes, key=lambda process: process.pid)


def _find_macos_reaper_processes(runner: Runner) -> list[ProcessInfo]:
    result = runner(["ps", "-axo", "pid=,comm="])
    if result.returncode != 0:
        raise ProcessDetectionError(
            f"Could not determine whether REAPER is running: ps failed with exit code {result.returncode}."
        )

    processes: list[ProcessInfo] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if not pid_text or not command.strip():
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            raise ProcessDetectionError(f"Could not parse ps PID value: {pid_text!r}")
        command = command.strip()
        if _matches_reaper_name(command):
            processes.append(ProcessInfo(pid=pid, name=Path(command).name, command=command))
    return sorted(processes, key=lambda process: process.pid)


def find_reaper_processes(
    *,
    platform: str,
    proc_root: str | Path = "/proc",
    runner: Runner | None = None,
) -> list[ProcessInfo]:
    normalized = platform.lower()
    if normalized.startswith("linux"):
        return _find_linux_reaper_processes(Path(proc_root))
    if normalized.startswith("win"):
        return _find_windows_reaper_processes(runner or _default_runner)
    if normalized == "darwin":
        return _find_macos_reaper_processes(runner or _default_runner)
    raise ProcessDetectionError(f"Unsupported platform for REAPER detection: {platform}")


def is_reaper_running(
    *,
    platform: str,
    proc_root: str | Path = "/proc",
    runner: Runner | None = None,
) -> bool:
    return bool(find_reaper_processes(platform=platform, proc_root=proc_root, runner=runner))
