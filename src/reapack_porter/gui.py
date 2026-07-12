from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
import sys

from .gui_state import (
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
from .operations import DEFAULT_DEPS, ExportResult, ImportPlan, ImportResult, export_repositories, import_repositories, preview_import
from .paths import ResolvedIniPath, STATUS_MANUAL, open_path, resolve_reapack_ini_path
from .settings import (
    AppSettings,
    load_settings,
    remember_bundle_path,
    remember_ini_path,
    remember_output_dir,
    save_settings,
)


def _load_tk_modules():
    tk = importlib.import_module("tkinter")
    ttk = importlib.import_module("tkinter.ttk")
    filedialog = importlib.import_module("tkinter.filedialog")
    messagebox = importlib.import_module("tkinter.messagebox")
    return tk, ttk, filedialog, messagebox


@dataclass(frozen=True)
class GuiDeps:
    export_repositories: callable
    preview_import: callable
    import_repositories: callable
    default_reapack_ini_path: callable
    default_documents_dir: callable
    is_reaper_running: callable
    open_path: callable
    resolve_reapack_ini_path: callable
    load_settings: callable
    save_settings: callable
    remember_ini_path: callable
    remember_output_dir: callable
    remember_bundle_path: callable


DEFAULT_GUI_DEPS = GuiDeps(
    export_repositories=export_repositories,
    preview_import=preview_import,
    import_repositories=import_repositories,
    default_reapack_ini_path=DEFAULT_DEPS.default_reapack_ini_path,
    default_documents_dir=DEFAULT_DEPS.default_documents_dir,
    is_reaper_running=DEFAULT_DEPS.is_reaper_running,
    open_path=open_path,
    resolve_reapack_ini_path=resolve_reapack_ini_path,
    load_settings=load_settings,
    save_settings=save_settings,
    remember_ini_path=remember_ini_path,
    remember_output_dir=remember_output_dir,
    remember_bundle_path=remember_bundle_path,
)


class ReaPackPorterApp:
    def __init__(self, root, *, tk, ttk, filedialog, messagebox, ops: GuiDeps = DEFAULT_GUI_DEPS, platform: str | None = None) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.ops = ops
        self.platform = platform or sys.platform
        self.root.title("ReaPack Porter")
        self.root.geometry("720x480")

        self.last_export_result: ExportResult | None = None
        self.last_preview: ImportPlan | None = None
        self.preview_stale = True
        self.reaper_status = REAPER_UNKNOWN
        self.settings = AppSettings()
        self.source_status = None
        self.target_status = None

        self.source_var = tk.StringVar(value="")
        self.output_var = tk.StringVar(value="")
        self.create_zip_var = tk.BooleanVar(value=True)
        self.keep_folder_var = tk.BooleanVar(value=False)
        self.export_status_var = tk.StringVar(value="")
        self.source_status_var = tk.StringVar(value="")
        self.target_status_var = tk.StringVar(value="")

        self.bundle_var = tk.StringVar(value="")
        self.target_var = tk.StringVar(value="")
        self.import_status_var = tk.StringVar(value="")
        self.preview_var = tk.StringVar(value="")
        self.reaper_status_var = tk.StringVar(value=reaper_status_text(REAPER_UNKNOWN))

        self._build()
        self._load_settings()
        self._set_default_paths()
        self._refresh_export_controls()
        self._refresh_import_status()

    def _build(self) -> None:
        notebook = self.ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True)
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.export_tab = self.ttk.Frame(notebook, padding=12)
        self.import_tab = self.ttk.Frame(notebook, padding=12)
        notebook.add(self.export_tab, text="Export")
        notebook.add(self.import_tab, text="Import")

        self._build_export_tab()
        self._build_import_tab()

    def _build_export_tab(self) -> None:
        self.ttk.Label(self.export_tab, text="Export ReaPack repositories").grid(row=0, column=0, columnspan=3, sticky="w")
        self.ttk.Label(self.export_tab, text="Source reapack.ini").grid(row=1, column=0, sticky="w")
        self.ttk.Entry(self.export_tab, textvariable=self.source_var, width=60).grid(row=2, column=0, sticky="ew")
        self.ttk.Button(self.export_tab, text="Browse...", command=self._browse_source).grid(row=2, column=1, padx=(8, 0))
        self.ttk.Label(self.export_tab, textvariable=self.source_status_var).grid(row=2, column=2, sticky="w", padx=(8, 0))
        self.ttk.Label(self.export_tab, text="Output folder").grid(row=3, column=0, sticky="w", pady=(12, 0))
        self.ttk.Entry(self.export_tab, textvariable=self.output_var, width=60).grid(row=4, column=0, sticky="ew")
        self.ttk.Button(self.export_tab, text="Browse...", command=self._browse_output).grid(row=4, column=1, padx=(8, 0))
        self.create_zip_check = self.ttk.Checkbutton(self.export_tab, text="Create ZIP file", variable=self.create_zip_var, command=self._refresh_export_controls)
        self.create_zip_check.grid(row=5, column=0, sticky="w", pady=(12, 0))
        self.keep_folder_check = self.ttk.Checkbutton(self.export_tab, text="Keep folder after ZIP", variable=self.keep_folder_var)
        self.keep_folder_check.grid(row=6, column=0, sticky="w")
        self.export_button = self.ttk.Button(self.export_tab, text="Export", command=self._do_export)
        self.export_button.grid(row=7, column=0, sticky="w", pady=(12, 0))
        self.ttk.Button(self.export_tab, text="Reset paths", command=self._set_default_paths).grid(row=7, column=1, sticky="w", padx=(8, 0))
        self.open_output_button = self.ttk.Button(self.export_tab, text="Open output folder", command=self._open_output)
        self.open_output_button.grid(row=8, column=0, sticky="w", pady=(8, 0))
        self.ttk.Label(self.export_tab, textvariable=self.export_status_var, wraplength=620).grid(row=9, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.export_tab.columnconfigure(0, weight=1)

        self.source_var.trace_add("write", lambda *_: self._refresh_export_controls())
        self.output_var.trace_add("write", lambda *_: self._refresh_export_controls())

    def _build_import_tab(self) -> None:
        self.ttk.Label(self.import_tab, text="Import ReaPack repositories").grid(row=0, column=0, columnspan=4, sticky="w")
        self.ttk.Label(self.import_tab, text="Bundle folder or ZIP file").grid(row=1, column=0, sticky="w")
        self.ttk.Entry(self.import_tab, textvariable=self.bundle_var, width=60).grid(row=2, column=0, sticky="ew")
        self.ttk.Button(self.import_tab, text="Browse ZIP...", command=self._browse_bundle_zip).grid(row=2, column=1, padx=(8, 0))
        self.ttk.Button(self.import_tab, text="Browse folder...", command=self._browse_bundle_folder).grid(row=2, column=2, padx=(8, 0))
        self.ttk.Label(self.import_tab, text="Target reapack.ini").grid(row=3, column=0, sticky="w", pady=(12, 0))
        self.ttk.Entry(self.import_tab, textvariable=self.target_var, width=60).grid(row=4, column=0, sticky="ew")
        self.ttk.Button(self.import_tab, text="Browse...", command=self._browse_target).grid(row=4, column=1, padx=(8, 0))
        self.ttk.Label(self.import_tab, textvariable=self.target_status_var).grid(row=4, column=2, sticky="w", padx=(8, 0))
        self.ttk.Button(self.import_tab, text="Preview", command=self._do_preview).grid(row=5, column=0, sticky="w", pady=(12, 0))
        self.ttk.Label(self.import_tab, textvariable=self.preview_var, wraplength=620).grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.ttk.Label(self.import_tab, textvariable=self.reaper_status_var).grid(row=7, column=0, sticky="w", pady=(12, 0))
        self.ttk.Button(self.import_tab, text="Refresh REAPER status", command=self._refresh_import_status).grid(row=7, column=1, sticky="w", padx=(8, 0))
        self.import_button = self.ttk.Button(self.import_tab, text="Import", command=self._do_import)
        self.import_button.grid(row=8, column=0, sticky="w", pady=(12, 0))
        self.ttk.Button(self.import_tab, text="Reset target", command=self._reset_target).grid(row=8, column=1, sticky="w", padx=(8, 0))
        self.ttk.Label(self.import_tab, textvariable=self.import_status_var, wraplength=620).grid(row=9, column=0, columnspan=4, sticky="w", pady=(12, 0))
        self.import_tab.columnconfigure(0, weight=1)

        self.bundle_var.trace_add("write", lambda *_: self._mark_preview_stale())
        self.target_var.trace_add("write", lambda *_: self._mark_preview_stale())

    def _load_settings(self) -> None:
        env = dict(os.environ)
        home = Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
        self.settings = self.ops.load_settings(platform=self.platform, home=home, env=env)

    def _save_settings(self) -> None:
        env = dict(os.environ)
        home = Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
        self.ops.save_settings(self.settings, platform=self.platform, home=home, env=env)

    def _set_source_resolution(self, resolution: ResolvedIniPath) -> None:
        self.source_status = resolution
        self.source_var.set(str(resolution.path))
        self.source_status_var.set(path_status_text(resolution.status))

    def _set_target_resolution(self, resolution: ResolvedIniPath) -> None:
        self.target_status = resolution
        self.target_var.set(str(resolution.path))
        self.target_status_var.set(path_status_text(resolution.status))

    def _set_default_paths(self) -> None:
        env = dict(os.environ)
        home = Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
        cwd = Path.cwd()
        source_resolution = self.ops.resolve_reapack_ini_path(
            platform=self.platform,
            home=home,
            env=env,
            remembered_path=self.settings.source_ini,
            cwd=cwd,
        )
        target_resolution = self.ops.resolve_reapack_ini_path(
            platform=self.platform,
            home=home,
            env=env,
            remembered_path=self.settings.target_ini,
            cwd=cwd,
        )
        self._set_source_resolution(source_resolution)
        self._set_target_resolution(target_resolution)
        if self.settings.output_dir and Path(self.settings.output_dir).exists():
            self.output_var.set(self.settings.output_dir)
        else:
            self.output_var.set(str(self.ops.default_documents_dir(platform=self.platform, home=home, cwd=cwd)))
        if self.settings.bundle_path:
            self.bundle_var.set(self.settings.bundle_path)
        self._refresh_export_controls()
        self._mark_preview_stale()

    def _reset_target(self) -> None:
        env = dict(os.environ)
        home = Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
        resolution = self.ops.resolve_reapack_ini_path(platform=self.platform, home=home, env=env, cwd=Path.cwd())
        self._set_target_resolution(resolution)
        self._mark_preview_stale()

    def _reset_source(self) -> None:
        env = dict(os.environ)
        home = Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
        resolution = self.ops.resolve_reapack_ini_path(platform=self.platform, home=home, env=env, cwd=Path.cwd())
        self._set_source_resolution(resolution)
        self._refresh_export_controls()

    def _refresh_export_controls(self) -> None:
        if keep_folder_enabled(self.create_zip_var.get()):
            self.keep_folder_check.state(["!disabled"])
        else:
            self.keep_folder_var.set(False)
            self.keep_folder_check.state(["disabled"])
        if export_enabled(self.source_var.get(), self.output_var.get(), source_exists=self._source_exists()):
            self.export_button.state(["!disabled"])
        else:
            self.export_button.state(["disabled"])
        if self.last_export_result is None:
            self.open_output_button.state(["disabled"])
        else:
            self.open_output_button.state(["!disabled"])

    def _mark_preview_stale(self) -> None:
        self.preview_stale = True
        self.last_preview = None
        self.preview_var.set("")
        self._update_import_button()

    def _refresh_import_status(self) -> None:
        try:
            running = self.ops.is_reaper_running(platform=self.platform)
        except Exception:
            self.reaper_status = REAPER_UNKNOWN
        else:
            self.reaper_status = REAPER_RUNNING if running else REAPER_CLOSED
        self.reaper_status_var.set(reaper_status_text(self.reaper_status))
        self._update_import_button()

    def _update_import_button(self) -> None:
        preview_state = GuiPreviewState(
            available=self.last_preview is not None,
            stale=self.preview_stale,
            reaper_status=self.reaper_status,
        )
        if import_enabled(self.bundle_var.get(), self.target_var.get(), preview_state, target_exists=self._target_exists()):
            self.import_button.state(["!disabled"])
        else:
            self.import_button.state(["disabled"])

    def _source_exists(self) -> bool:
        return Path(self.source_var.get()).is_file()

    def _target_exists(self) -> bool:
        return Path(self.target_var.get()).is_file()

    def _browse_source(self) -> None:
        path = self.filedialog.askopenfilename(filetypes=[("ReaPack configuration", "reapack.ini"), ("All files", "*")])
        if path:
            resolution = self.ops.resolve_reapack_ini_path(
                platform=self.platform,
                home=Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or Path.home()),
                env=dict(os.environ),
                explicit_path=path,
            )
            self._set_source_resolution(resolution)
            self.settings = self.ops.remember_ini_path(self.settings, "source_ini", path)
            self._save_settings()
            self._refresh_export_controls()

    def _browse_output(self) -> None:
        path = self.filedialog.askdirectory()
        if path:
            self.output_var.set(path)
            self.settings = self.ops.remember_output_dir(self.settings, path)
            self._save_settings()

    def _browse_bundle_zip(self) -> None:
        path = self.filedialog.askopenfilename(filetypes=[("ZIP files", "*.zip"), ("All files", "*")])
        if path:
            self.bundle_var.set(path)
            self.settings = self.ops.remember_bundle_path(self.settings, path)
            self._save_settings()

    def _browse_bundle_folder(self) -> None:
        path = self.filedialog.askdirectory()
        if path:
            self.bundle_var.set(path)
            self.settings = self.ops.remember_bundle_path(self.settings, path)
            self._save_settings()

    def _browse_target(self) -> None:
        path = self.filedialog.askopenfilename(filetypes=[("ReaPack configuration", "reapack.ini"), ("All files", "*")])
        if path:
            resolution = self.ops.resolve_reapack_ini_path(
                platform=self.platform,
                home=Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or Path.home()),
                env=dict(os.environ),
                explicit_path=path,
            )
            self._set_target_resolution(resolution)
            self.settings = self.ops.remember_ini_path(self.settings, "target_ini", path)
            self._save_settings()
            self._mark_preview_stale()

    def _open_output(self) -> None:
        if self.last_export_result is None:
            return
        target = self.last_export_result.zip_path or self.last_export_result.bundle_path
        try:
            self.ops.open_path(target, platform=self.platform)
        except RuntimeError as exc:
            self.export_status_var.set(str(exc))

    def _do_export(self) -> None:
        try:
            result = self.ops.export_repositories(
                source=self.source_var.get(),
                output_dir=self.output_var.get(),
                create_zip=self.create_zip_var.get(),
                keep_folder=self.keep_folder_var.get(),
                platform=self.platform,
            )
        except Exception as exc:
            self.export_status_var.set(str(exc))
            self.messagebox.showerror("ReaPack Porter", str(exc))
            return
        self.last_export_result = result
        self.settings = self.ops.remember_ini_path(self.settings, "source_ini", self.source_var.get())
        self.settings = self.ops.remember_output_dir(self.settings, self.output_var.get())
        self._save_settings()
        self.export_status_var.set(
            f"Repositories: {result.repository_count}\nBundle: {result.bundle_path}\nZIP: {result.zip_path or 'not created'}"
        )
        self._refresh_export_controls()

    def _do_preview(self) -> None:
        try:
            plan = self.ops.preview_import(
                bundle=self.bundle_var.get(),
                target=self.target_var.get(),
                platform=self.platform,
            )
        except Exception as exc:
            self.import_status_var.set(str(exc))
            self.messagebox.showerror("ReaPack Porter", str(exc))
            return
        self.last_preview = plan
        self.preview_stale = False
        self.settings = self.ops.remember_bundle_path(self.settings, self.bundle_var.get())
        self._save_settings()
        self.preview_var.set(
            f"Repositories in bundle: {plan.imported_count}\nAdded: {plan.added_count}\nSkipped: {plan.skipped_count}\nResulting total: {plan.total_count}"
        )
        self._update_import_button()

    def _do_import(self) -> None:
        try:
            result: ImportResult = self.ops.import_repositories(
                bundle=self.bundle_var.get(),
                target=self.target_var.get(),
                platform=self.platform,
            )
        except (InvalidInputError, ReaperRunningError, ReaperDetectionError, Exception) as exc:
            self.import_status_var.set(str(exc))
            self.messagebox.showerror("ReaPack Porter", str(exc))
            self._refresh_import_status()
            return
        self.import_status_var.set(
            f"Target: {result.target_path}\nBackup: {result.backup_path}\nAdded: {result.added_count}\nSkipped: {result.skipped_count}\nTotal: {result.total_count}"
        )
        self.settings = self.ops.remember_ini_path(self.settings, "target_ini", self.target_var.get())
        self.settings = self.ops.remember_bundle_path(self.settings, self.bundle_var.get())
        self._save_settings()
        self.preview_stale = True
        self.last_preview = None
        self.preview_var.set("Import completed. Run Preview again to refresh counts.")
        self._refresh_import_status()

    def _on_tab_changed(self, event) -> None:
        try:
            current = event.widget.tab(event.widget.select(), "text")
        except Exception:
            return
        if current == "Import":
            self._refresh_import_status()


def main(*, stderr=None, start_mainloop: bool = True, root_factory=None, tk_loader=_load_tk_modules, ops: GuiDeps = DEFAULT_GUI_DEPS) -> int:
    stderr = stderr or sys.stderr
    try:
        tk, ttk, filedialog, messagebox = tk_loader()
        root = root_factory() if root_factory is not None else tk.Tk()
    except Exception as exc:
        print(f"Tkinter GUI is not available: {exc}", file=stderr)
        return 5

    ReaPackPorterApp(root, tk=tk, ttk=ttk, filedialog=filedialog, messagebox=messagebox, ops=ops)
    if start_mainloop:
        root.mainloop()
    return 0
