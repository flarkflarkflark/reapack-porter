from __future__ import annotations

from dataclasses import dataclass


REAPER_CLOSED = "closed"
REAPER_RUNNING = "running"
REAPER_UNKNOWN = "unknown"
PATH_DETECTED = "detected"
PATH_REMEMBERED = "remembered"
PATH_EXPECTED = "expected_missing"
PATH_MANUAL = "manual"


@dataclass(frozen=True)
class GuiPreviewState:
    available: bool
    stale: bool
    reaper_status: str


def export_enabled(source: str, output_dir: str) -> bool:
    return bool(source.strip()) and bool(output_dir.strip())


def keep_folder_enabled(create_zip: bool) -> bool:
    return create_zip


def path_status_text(status: str) -> str:
    if status == PATH_DETECTED:
        return "Detected"
    if status == PATH_REMEMBERED:
        return "Remembered"
    if status == PATH_MANUAL:
        return "Selected manually"
    return "Expected location — file not found"


def reaper_status_text(status: str) -> str:
    if status == REAPER_CLOSED:
        return "REAPER is closed"
    if status == REAPER_RUNNING:
        return "REAPER is running"
    return "REAPER status could not be determined"


def import_enabled(bundle: str, target: str, preview: GuiPreviewState, *, target_exists: bool = True) -> bool:
    return (
        bool(bundle.strip())
        and bool(target.strip())
        and target_exists
        and preview.available
        and not preview.stale
        and preview.reaper_status == REAPER_CLOSED
    )


def export_enabled(source: str, output_dir: str, *, source_exists: bool = True) -> bool:
    return bool(source.strip()) and bool(output_dir.strip()) and source_exists
