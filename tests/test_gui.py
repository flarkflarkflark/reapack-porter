from __future__ import annotations

import importlib
from io import StringIO
from pathlib import Path
import sys

from reapack_porter.gui import main
from reapack_porter.gui_state import (
    PATH_DETECTED,
    PATH_EXPECTED,
    PATH_MANUAL,
    PATH_REMEMBERED,
    GuiPreviewState,
    REAPER_CLOSED,
    REAPER_RUNNING,
    REAPER_UNKNOWN,
    export_enabled,
    import_enabled,
    keep_folder_enabled,
    path_status_text,
    reaper_status_text,
)


def test_import_gui_module_does_not_create_root(monkeypatch) -> None:
    import tkinter

    def fail(*args, **kwargs):
        raise AssertionError("Tk should not be constructed on import")

    monkeypatch.setattr(tkinter, "Tk", fail)
    sys.modules.pop("reapack_porter.gui", None)
    module = importlib.import_module("reapack_porter.gui")
    assert module is not None


def test_gui_entrypoint_present_in_pyproject() -> None:
    import tomllib

    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["gui-scripts"]["reapack-porter-gui"] == "reapack_porter.gui:main"


def test_gui_main_reports_missing_tk_without_traceback() -> None:
    stderr = StringIO()

    def loader():
        raise RuntimeError("no display")

    code = main(stderr=stderr, start_mainloop=False, tk_loader=loader)
    assert code != 0
    assert "Tkinter GUI is not available:" in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()


def test_status_mapping() -> None:
    assert reaper_status_text(REAPER_CLOSED) == "REAPER is closed"
    assert reaper_status_text(REAPER_RUNNING) == "REAPER is running"
    assert reaper_status_text(REAPER_UNKNOWN) == "REAPER status could not be determined"
    assert path_status_text(PATH_DETECTED) == "Detected"
    assert path_status_text(PATH_REMEMBERED) == "Remembered"
    assert path_status_text(PATH_EXPECTED) == "Expected location — file not found"
    assert path_status_text(PATH_MANUAL) == "Selected manually"


def test_import_enabled_requires_preview_and_closed_status() -> None:
    preview = GuiPreviewState(available=True, stale=False, reaper_status=REAPER_CLOSED)
    assert import_enabled("bundle.zip", "reapack.ini", preview, target_exists=True) is True
    assert import_enabled("bundle.zip", "reapack.ini", GuiPreviewState(True, True, REAPER_CLOSED), target_exists=True) is False
    assert import_enabled("bundle.zip", "reapack.ini", GuiPreviewState(True, False, REAPER_RUNNING), target_exists=True) is False
    assert import_enabled("", "reapack.ini", preview, target_exists=True) is False
    assert import_enabled("bundle.zip", "reapack.ini", preview, target_exists=False) is False


def test_export_enabled_and_keep_folder_state() -> None:
    assert export_enabled("source.ini", "out", source_exists=True) is True
    assert export_enabled("", "out", source_exists=True) is False
    assert export_enabled("source.ini", "out", source_exists=False) is False
    assert keep_folder_enabled(True) is True
    assert keep_folder_enabled(False) is False
