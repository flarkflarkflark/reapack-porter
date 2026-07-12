from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from reapack_porter.processes import ProcessDetectionError, find_reaper_processes, is_reaper_running


def _proc_entry(root: Path, pid: int, *, comm: str, cmdline: list[str]) -> None:
    pid_dir = root / str(pid)
    pid_dir.mkdir(parents=True)
    (pid_dir / "comm").write_text(comm + "\n", encoding="utf-8")
    (pid_dir / "cmdline").write_bytes(b"\0".join(part.encode("utf-8") for part in cmdline) + b"\0")


def test_linux_process_detection_matches_reaper_and_wine(tmp_path: Path) -> None:
    _proc_entry(tmp_path, 100, comm="REAPER", cmdline=["/opt/REAPER/reaper"])
    _proc_entry(tmp_path, 101, comm="wine64-preloader", cmdline=["wine64", "C:\\Program Files\\REAPER\\reaper.exe"])
    _proc_entry(tmp_path, 102, comm="python", cmdline=["python", "reapack-porter", "reaper"])
    _proc_entry(tmp_path, 103, comm="reaper-helper-test", cmdline=["reaper-helper-test"])

    found = find_reaper_processes(platform="linux", proc_root=tmp_path)
    assert [process.pid for process in found] == [100, 101]


def test_linux_process_detection_skips_disappearing_entries(tmp_path: Path) -> None:
    pid_dir = tmp_path / "200"
    pid_dir.mkdir()
    (pid_dir / "comm").write_text("reaper\n", encoding="utf-8")
    found = find_reaper_processes(platform="linux", proc_root=tmp_path)
    assert found == []


def test_linux_process_detection_reports_unusable_proc_root(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing-proc"
    with pytest.raises(ProcessDetectionError, match="could not inspect"):
        find_reaper_processes(platform="linux", proc_root=missing_root)


def test_windows_process_detection_parses_tasklist() -> None:
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args == ["tasklist", "/fo", "csv", "/nh"]
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout='"REAPER.exe","1234","Console","1","42,000 K"\n"python.exe","1","Console","1","10 K"\n',
            stderr="",
        )

    found = find_reaper_processes(platform="win32", runner=runner)
    assert len(found) == 1
    assert found[0].pid == 1234


def test_windows_process_detection_reports_runner_failure() -> None:
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="tasklist failed")

    with pytest.raises(ProcessDetectionError, match="tasklist failed"):
        find_reaper_processes(platform="windows", runner=runner)


def test_windows_process_detection_reports_missing_tasklist() -> None:
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        raise ProcessDetectionError("Could not determine whether REAPER is running: failed to launch tasklist.")

    with pytest.raises(ProcessDetectionError, match="failed to launch tasklist"):
        find_reaper_processes(platform="windows", runner=runner)


def test_macos_process_detection_parses_ps() -> None:
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args == ["ps", "-axo", "pid=,comm="]
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=" 123 /Applications/REAPER.app/Contents/MacOS/REAPER\n 456 /usr/bin/python3\n",
            stderr="",
        )

    found = find_reaper_processes(platform="darwin", runner=runner)
    assert len(found) == 1
    assert found[0].pid == 123


def test_unknown_platform_reports_detection_error() -> None:
    with pytest.raises(ProcessDetectionError, match="Unsupported platform"):
        find_reaper_processes(platform="plan9")


def test_is_reaper_running_false_when_no_processes(tmp_path: Path) -> None:
    assert is_reaper_running(platform="linux", proc_root=tmp_path) is False
