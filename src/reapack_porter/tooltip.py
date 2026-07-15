from __future__ import annotations

import tkinter as tk


DEFAULT_DELAY_MS = 600
DEFAULT_WRAP_LENGTH = 360

_ACTIVE_TOOLTIP: "Tooltip | None" = None
_TOOLTIPS: list["Tooltip"] = []
_MOTION_BOUND_WIDGET_IDS: set[int] = set()


def _dispatch_motion(event=None) -> None:
    del event
    for tooltip in tuple(_TOOLTIPS):
        tooltip._motion_event()


class Tooltip:
    def __init__(self, widget, text: str, *, delay_ms: int = DEFAULT_DELAY_MS, wrap_length: int = DEFAULT_WRAP_LENGTH) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.wrap_length = wrap_length
        self.after_id = None
        self.tip_window = None
        self.pointer_inside = False

        widget.bind("<Enter>", self._schedule_event, add="+")
        widget.bind("<Leave>", self._hide_event, add="+")
        widget.bind("<ButtonPress>", self._hide_event, add="+")
        widget.bind("<Destroy>", self._destroy_event, add="+")
        widget.bind("<Escape>", self._hide_event, add="+")
        _TOOLTIPS.append(self)
        self._bind_global_motion_once()

    def _bind_global_motion_once(self) -> None:
        root = self.widget._root()
        root_id = id(root)
        if root_id in _MOTION_BOUND_WIDGET_IDS:
            return
        root.bind_all("<Motion>", _dispatch_motion, add="+")
        _MOTION_BOUND_WIDGET_IDS.add(root_id)

    def _schedule_event(self, event=None) -> None:
        del event
        self.pointer_inside = True
        self._schedule()

    def _hide_event(self, event=None) -> None:
        del event
        self.pointer_inside = False
        self._hide()

    def _destroy_event(self, event=None) -> None:
        del event
        self._on_destroy()

    def _motion_event(self, event=None) -> None:
        del event
        inside = self._pointer_inside_widget()
        if inside and not self.pointer_inside:
            self.pointer_inside = True
            self._schedule()
        elif not inside and self.pointer_inside:
            self.pointer_inside = False
            self._hide()

    def _schedule(self) -> None:
        self._cancel_pending()
        self.after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel_pending(self) -> None:
        if self.after_id is None:
            return
        try:
            self.widget.after_cancel(self.after_id)
        except tk.TclError:
            pass
        self.after_id = None

    def _widget_exists(self) -> bool:
        try:
            return bool(self.widget.winfo_exists())
        except tk.TclError:
            return False

    def _pointer_inside_widget(self) -> bool:
        if not self._widget_exists():
            return False
        try:
            pointer_x = self.widget.winfo_pointerx()
            pointer_y = self.widget.winfo_pointery()
            widget_x = self.widget.winfo_rootx()
            widget_y = self.widget.winfo_rooty()
            width = self.widget.winfo_width()
            height = self.widget.winfo_height()
        except tk.TclError:
            return False
        return widget_x <= pointer_x < widget_x + width and widget_y <= pointer_y < widget_y + height

    def _show(self) -> None:
        global _ACTIVE_TOOLTIP
        self.after_id = None
        if self.tip_window is not None or not self.text or not self._widget_exists():
            return
        if _ACTIVE_TOOLTIP is not None and _ACTIVE_TOOLTIP is not self:
            _ACTIVE_TOOLTIP._hide()
        _ACTIVE_TOOLTIP = self

        window = tk.Toplevel(self.widget)
        window.withdraw()
        window.overrideredirect(True)
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass

        label = tk.Label(
            window,
            text=self.text,
            justify="left",
            wraplength=self.wrap_length,
            padx=8,
            pady=5,
            relief="solid",
            borderwidth=1,
            background="#ffffe8",
            foreground="#000000",
        )
        label.pack()
        window.update_idletasks()

        x, y = self._position(window)
        window.geometry(f"+{x}+{y}")
        window.deiconify()
        self.tip_window = window

    def _position(self, window) -> tuple[int, int]:
        pointer_x = self.widget.winfo_pointerx()
        pointer_y = self.widget.winfo_pointery()
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()

        x = pointer_x + 14
        y = pointer_y + 18
        if x + width + 8 > screen_width:
            x = max(0, screen_width - width - 8)
        if y + height + 8 > screen_height:
            y = max(0, pointer_y - height - 12)
        return x, y

    def _hide(self) -> None:
        global _ACTIVE_TOOLTIP
        self._cancel_pending()
        if self.tip_window is not None:
            try:
                self.tip_window.destroy()
            except tk.TclError:
                pass
            self.tip_window = None
        if _ACTIVE_TOOLTIP is self:
            _ACTIVE_TOOLTIP = None

    def _on_destroy(self) -> None:
        self._hide()
        if self in _TOOLTIPS:
            _TOOLTIPS.remove(self)
