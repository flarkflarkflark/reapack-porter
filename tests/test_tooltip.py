from __future__ import annotations

import importlib
import sys


class FakeWidget:
    def __init__(self) -> None:
        self.bindings = {}
        self.cancelled = []
        self.destroyed = False
        self.after_callback = None
        self.pointer_x = 40
        self.pointer_y = 50
        self.root_x = 10
        self.root_y = 20
        self.width = 100
        self.height = 40

    def _root(self):
        return self

    def bind(self, event, callback, add=None):
        self.bindings[event] = (callback, add)

    def bind_all(self, event, callback, add=None):
        self.bindings[f"all:{event}"] = (callback, add)

    def after(self, delay, callback):
        self.after_delay = delay
        self.after_callback = callback
        return "after-1"

    def after_cancel(self, after_id):
        self.cancelled.append(after_id)

    def winfo_exists(self):
        return not self.destroyed

    def winfo_pointerx(self):
        return self.pointer_x

    def winfo_pointery(self):
        return self.pointer_y

    def winfo_rootx(self):
        return self.root_x

    def winfo_rooty(self):
        return self.root_y

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def winfo_screenwidth(self):
        return 800

    def winfo_screenheight(self):
        return 600


class FakeTipWindow:
    instances = []

    def __init__(self, widget):
        self.widget = widget
        self.destroyed = False
        self.geometry_value = None
        self.overrideredirect_value = None
        self.attributes_calls = []
        FakeTipWindow.instances.append(self)

    def withdraw(self):
        self.withdrawn = True

    def overrideredirect(self, value):
        self.overrideredirect_value = value

    def attributes(self, *args):
        self.attributes_calls.append(args)

    def update_idletasks(self):
        pass

    def winfo_reqwidth(self):
        return 120

    def winfo_reqheight(self):
        return 40

    def geometry(self, value):
        self.geometry_value = value

    def deiconify(self):
        self.deiconified = True

    def destroy(self):
        self.destroyed = True


class FakeLabel:
    def __init__(self, window, **kwargs):
        self.window = window
        self.kwargs = kwargs

    def pack(self, **kwargs):
        self.pack_kwargs = kwargs


def test_import_tooltip_module_does_not_create_root(monkeypatch) -> None:
    import tkinter

    def fail(*args, **kwargs):
        raise AssertionError("Tk should not be constructed on import")

    monkeypatch.setattr(tkinter, "Tk", fail)
    sys.modules.pop("reapack_porter.tooltip", None)
    module = importlib.import_module("reapack_porter.tooltip")
    assert module is not None


def test_default_delay_is_not_immediate_and_reasonable() -> None:
    from reapack_porter.tooltip import DEFAULT_DELAY_MS

    assert 500 <= DEFAULT_DELAY_MS <= 700


def test_tooltip_binds_hover_press_destroy_and_escape_events() -> None:
    from reapack_porter.tooltip import Tooltip

    widget = FakeWidget()
    Tooltip(widget, "Helpful text")

    assert "<Enter>" in widget.bindings
    assert "<Leave>" in widget.bindings
    assert "<ButtonPress>" in widget.bindings
    assert "<Destroy>" in widget.bindings
    assert "<Escape>" in widget.bindings
    assert "all:<Motion>" in widget.bindings


def test_tooltips_share_one_global_motion_binding() -> None:
    from reapack_porter import tooltip as tooltip_module

    tooltip_module._TOOLTIPS.clear()
    tooltip_module._MOTION_BOUND_WIDGET_IDS.clear()
    root = FakeWidget()
    first = tooltip_module.Tooltip(root, "First")
    second = tooltip_module.Tooltip(root, "Second")

    assert len([key for key in root.bindings if key == "all:<Motion>"]) == 1
    assert first in tooltip_module._TOOLTIPS
    assert second in tooltip_module._TOOLTIPS


def test_leave_cancels_pending_show() -> None:
    from reapack_porter.tooltip import Tooltip

    widget = FakeWidget()
    tooltip = Tooltip(widget, "Helpful text", delay_ms=600)

    tooltip._schedule()
    tooltip._hide()

    assert widget.cancelled == ["after-1"]


def test_destroy_cancels_pending_show_safely() -> None:
    from reapack_porter import tooltip as tooltip_module

    widget = FakeWidget()
    tooltip_module._TOOLTIPS.clear()
    tooltip = tooltip_module.Tooltip(widget, "Helpful text", delay_ms=600)

    tooltip._schedule()
    widget.destroyed = True
    tooltip._on_destroy()

    assert widget.cancelled == ["after-1"]
    assert tooltip.tip_window is None
    assert tooltip not in tooltip_module._TOOLTIPS


def test_destroyed_widget_does_not_raise_when_showing(monkeypatch) -> None:
    from reapack_porter import tooltip as tooltip_module

    monkeypatch.setattr(tooltip_module.tk, "Toplevel", FakeTipWindow)
    widget = FakeWidget()
    widget.destroyed = True
    tooltip = tooltip_module.Tooltip(widget, "Helpful text")

    tooltip._show()

    assert FakeTipWindow.instances == []


def test_global_motion_schedules_tooltip_for_disabled_widget_path() -> None:
    from reapack_porter.tooltip import Tooltip

    widget = FakeWidget()
    widget.pointer_x = 30
    widget.pointer_y = 30
    tooltip = Tooltip(widget, "Helpful text", delay_ms=600)

    tooltip._motion_event()

    assert tooltip.pointer_inside is True
    assert tooltip.after_id == "after-1"


def test_global_motion_leave_hides_tooltip_for_disabled_widget_path() -> None:
    from reapack_porter.tooltip import Tooltip

    widget = FakeWidget()
    tooltip = Tooltip(widget, "Helpful text", delay_ms=600)
    tooltip.pointer_inside = True
    tooltip.after_id = "after-1"
    widget.pointer_x = 500
    widget.pointer_y = 500

    tooltip._motion_event()

    assert tooltip.pointer_inside is False
    assert widget.cancelled == ["after-1"]


def test_single_tooltip_instance_does_not_create_overlapping_windows(monkeypatch) -> None:
    from reapack_porter import tooltip as tooltip_module

    FakeTipWindow.instances = []
    monkeypatch.setattr(tooltip_module.tk, "Toplevel", FakeTipWindow)
    monkeypatch.setattr(tooltip_module.tk, "Label", FakeLabel)
    widget = FakeWidget()
    tooltip = tooltip_module.Tooltip(widget, "Helpful text")

    tooltip._show()
    tooltip._show()

    assert len(FakeTipWindow.instances) == 1
    assert FakeTipWindow.instances[0].overrideredirect_value is True
    assert FakeTipWindow.instances[0].geometry_value is not None


def test_opening_new_tooltip_hides_previous(monkeypatch) -> None:
    from reapack_porter import tooltip as tooltip_module

    FakeTipWindow.instances = []
    monkeypatch.setattr(tooltip_module.tk, "Toplevel", FakeTipWindow)
    monkeypatch.setattr(tooltip_module.tk, "Label", FakeLabel)
    first = tooltip_module.Tooltip(FakeWidget(), "First")
    second = tooltip_module.Tooltip(FakeWidget(), "Second")

    first._show()
    second._show()

    assert FakeTipWindow.instances[0].destroyed is True
    assert FakeTipWindow.instances[1].destroyed is False


def test_tooltip_module_contains_no_domain_logic() -> None:
    import reapack_porter.tooltip as tooltip_module

    text = tooltip_module.__file__
    assert text is not None
    source = open(text, encoding="utf-8").read()
    forbidden = ("export_repositories", "import_repositories", "is_reaper_running", "reapack.ini")
    assert not any(term in source for term in forbidden)
