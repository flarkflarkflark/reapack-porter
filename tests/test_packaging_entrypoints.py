from __future__ import annotations

import importlib.util
from pathlib import Path
import runpy
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
PYINSTALLER_DIR = ROOT / "tools" / "pyinstaller"


def _read(name: str) -> str:
    return (PYINSTALLER_DIR / name).read_text(encoding="utf-8")


def test_managed_spec_files_exist() -> None:
    assert (PYINSTALLER_DIR / "reapack_porter_gui.spec").is_file()
    assert (PYINSTALLER_DIR / "reapack_porter_cli.spec").is_file()


def test_specs_do_not_contain_developer_absolute_paths() -> None:
    for path in (PYINSTALLER_DIR / "reapack_porter_gui.spec", PYINSTALLER_DIR / "reapack_porter_cli.spec"):
        text = path.read_text(encoding="utf-8")
        assert "/home/" not in text
        assert "/Users/" not in text
        assert "C:\\" not in text


def test_gui_spec_static_contract() -> None:
    text = _read("reapack_porter_gui.spec")
    assert "console=False" in text
    assert "upx=False" in text
    assert "ReaPack-Porter" in text
    assert "gui_entry.py" in text
    assert "BUNDLE(" in text
    assert "ReaPack Porter.app" in text
    assert "io.github.flarkflarkflark.reapackporter" in text
    assert "COLLECT(" in text
    assert "EXE(" in text


def test_cli_spec_static_contract() -> None:
    text = _read("reapack_porter_cli.spec")
    assert "console=True" in text
    assert "upx=False" in text
    assert "reapack-porter-cli" in text
    assert "cli_entry.py" in text
    assert "COLLECT(" not in text


def test_wrapper_imports_do_not_start_apps(monkeypatch) -> None:
    gui_module = types.ModuleType("reapack_porter.gui")
    cli_module = types.ModuleType("reapack_porter.cli")
    gui_module.main = lambda: (_ for _ in ()).throw(AssertionError("GUI main should not run on import"))
    cli_module.main = lambda: (_ for _ in ()).throw(AssertionError("CLI main should not run on import"))
    monkeypatch.setitem(sys.modules, "reapack_porter.gui", gui_module)
    monkeypatch.setitem(sys.modules, "reapack_porter.cli", cli_module)

    for entry in ("gui_entry.py", "cli_entry.py"):
        spec = importlib.util.spec_from_file_location(entry.removesuffix(".py"), PYINSTALLER_DIR / entry)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


def test_gui_wrapper_delegates_to_gui_main(monkeypatch) -> None:
    called = {}
    gui_module = types.ModuleType("reapack_porter.gui")

    def main() -> int:
        called["gui"] = True
        return 7

    gui_module.main = main
    monkeypatch.setitem(sys.modules, "reapack_porter.gui", gui_module)

    try:
        runpy.run_path(str(PYINSTALLER_DIR / "gui_entry.py"), run_name="__main__")
    except SystemExit as exc:
        assert exc.code == 7

    assert called == {"gui": True}


def test_cli_wrapper_delegates_to_cli_main(monkeypatch) -> None:
    called = {}
    cli_module = types.ModuleType("reapack_porter.cli")

    def main() -> int:
        called["cli"] = True
        return 3

    cli_module.main = main
    monkeypatch.setitem(sys.modules, "reapack_porter.cli", cli_module)

    try:
        runpy.run_path(str(PYINSTALLER_DIR / "cli_entry.py"), run_name="__main__")
    except SystemExit as exc:
        assert exc.code == 3

    assert called == {"cli": True}


def test_wrappers_are_thin() -> None:
    gui_text = _read("gui_entry.py")
    cli_text = _read("cli_entry.py")
    assert gui_text == "from reapack_porter.gui import main\n\n\nif __name__ == \"__main__\":\n    raise SystemExit(main())\n"
    assert cli_text == "from reapack_porter.cli import main\n\n\nif __name__ == \"__main__\":\n    raise SystemExit(main())\n"


def test_gitignore_packaging_rules() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "dist/" in text
    assert "release/" in text
    assert ".pyinstaller-work/" in text
    assert "*.spec" in text
    assert "!tools/pyinstaller/*.spec" in text


def test_gui_tk_loader_uses_static_imports_for_pyinstaller_analysis() -> None:
    text = (ROOT / "src" / "reapack_porter" / "gui.py").read_text(encoding="utf-8")
    assert "importlib.import_module(\"tkinter" not in text
    assert "import tkinter as tk" in text
