"""
Anno 117 Map Template Editor - Tool Setup Dialog

Shown at startup when FileDBReader or RdaConsole are not found.
Offers three options:
  • Auto-Install from GitHub
  • Locate Manually (file dialog)
  • Skip for Now
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

import config
import filedb_handler as _fdb
import rda_handler
import tool_downloader


class ToolSetupDialog(tk.Toplevel):
    """
    Startup dialog for resolving missing external tools.
    Calls on_resolved({tool_name: path, ...}) when the user is done.
    """

    def __init__(
        self,
        root: tk.Tk,
        missing: List[str],
        on_resolved: Callable[[Dict[str, str]], None],
    ):
        super().__init__(root)
        self.title("Tool Setup")
        self.resizable(False, False)
        self.configure(bg=config.BG_SECTION)
        self.grab_set()

        self._missing = missing
        self._on_resolved = on_resolved

        # Per-tool state
        self._path_vars:     Dict[str, tk.StringVar]  = {}
        self._progress_vars: Dict[str, tk.DoubleVar]  = {}
        self._status_vars:   Dict[str, tk.StringVar]  = {}
        self._prog_widgets:  Dict[str, ttk.Progressbar] = {}
        self._stat_widgets:  Dict[str, tk.Label] = {}

        self._dl_btn:   Optional[tk.Button] = None
        self._skip_btn: Optional[tk.Button] = None

        self._build()
        self._centre()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self):
        # Header
        tk.Label(self, text="External Tools Not Found", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(padx=20, pady=(16, 4))

        names = " and ".join(self._missing)
        tk.Label(
            self,
            text=(f"{names} could not be located automatically.\n"
                  "Choose how to proceed:"),
            bg=config.BG_SECTION, fg=config.FG_MAIN,font=config.FONT_SMALL, justify="center").pack(padx=20, pady=(0, 10))

        # Tool rows
        for tool in self._missing:
            self._build_tool_row(tool)

        tk.Frame(self, bg=config.FG_SEPARATOR, height=1).pack(fill="x", padx=16, pady=10)

        # Install-path hint
        tk.Label(
            self,
            text=f"Auto-install destination: {config.TOOLS_INSTALL_DIR}",
            bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(padx=20, pady=(0, 6))

        # Buttons
        btn_row = tk.Frame(self, bg=config.BG_SECTION)
        btn_row.pack(padx=20, pady=(0, 16))

        self._dl_btn = tk.Button(
            btn_row, text="⬇  Auto-Install from GitHub",
            command=self._start_download,
            bg=config.FG_GOLD, fg=config.BG_MAIN, font=config.FONT_BOLD_SMALL, relief=tk.FLAT, padx=12, pady=5, cursor="hand2")
        self._dl_btn.pack(side="left", padx=4)

        self._skip_btn = tk.Button(
            btn_row, text="Skip for Now",
            command=self._skip,
            bg=config.BG_HOVER, fg=config.FG_DIM, font=config.FONT_SMALL, relief=tk.FLAT, padx=12, pady=5, cursor="hand2")
        self._skip_btn.pack(side="left", padx=4)

    def _build_tool_row(self, tool: str):
        outer = tk.Frame(self, bg=config.BG_MAIN, padx=10, pady=8)
        outer.pack(fill="x", padx=16, pady=3)

        # Row 0: label + entry + browse
        tk.Label(outer, text=tool, bg=config.BG_MAIN, fg=config.FG_GOLD, font=config.FONT_BOLD_SMALL, width=14, anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 6))

        path_var = tk.StringVar()
        self._path_vars[tool] = path_var

        tk.Entry(outer, textvariable=path_var, bg=config.BG_HOVER, fg=config.FG_MAIN, relief=tk.FLAT, font=config.FONT_XSMALL, width=30).grid(row=0, column=1, sticky="ew", padx=(0, 4))

        tk.Button(
            outer, text="Browse…",
            command=lambda t=tool: self._browse(t),
            bg=config.BG_HOVER, fg=config.FG_MAIN, font=config.FONT_XSMALL, relief=tk.FLAT, padx=6, cursor="hand2").grid(row=0, column=2)

        outer.columnconfigure(1, weight=1)

        # Row 1: progress bar + status label (hidden until download starts)
        prog_var = tk.DoubleVar(value=0.0)
        self._progress_vars[tool] = prog_var

        prog = ttk.Progressbar(outer, variable=prog_var, maximum=100, length=260)
        prog.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        prog.grid_remove()
        self._prog_widgets[tool] = prog

        status_var = tk.StringVar(value="")
        self._status_vars[tool] = status_var

        stat = tk.Label(
            outer, textvariable=status_var,
            bg=config.BG_MAIN, fg=config.FG_DIM,
            font=config.FONT_XSMALL, anchor="w",
        )
        stat.grid(row=1, column=2, sticky="w", padx=(6, 0), pady=(5, 0))
        stat.grid_remove()
        self._stat_widgets[tool] = stat

    # ── Actions ──────────────────────────────────────────────────────────────

    def _centre(self):
        self.update_idletasks()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_rootx()
        py = self.master.winfo_rooty()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _browse(self, tool: str):
        path = filedialog.askopenfilename(
            title=f"Select {tool} executable",
            filetypes=[("Executable", "*.exe"), ("All", "*")],
            parent=self,
        )
        if path:
            self._path_vars[tool].set(path)

    def _skip(self):
        result = {t: v.get().strip() for t, v in self._path_vars.items() if v.get().strip()}
        self._on_resolved(result)
        self.destroy()

    def _start_download(self):
        self._dl_btn.config(state="disabled", text="Downloading…")
        self._skip_btn.config(state="disabled")

        remaining = [len(self._missing)]
        results:   Dict[str, str] = {}
        errors:    Dict[str, str] = {}

        def _all_done():
            if errors:
                msg = "\n".join(f"• {t}: {e}" for t, e in errors.items())
                messagebox.showerror(
                    "Download Failed",
                    f"Some tools could not be downloaded:\n\n{msg}",
                    parent=self,
                )
            self._on_resolved(results)
            self.destroy()

        def _worker(tool: str):
            # Show progress row
            self.after(0, lambda: self._prog_widgets[tool].grid())
            self.after(0, lambda: self._stat_widgets[tool].grid())

            def _progress(done: int, total: int):
                if total > 0:
                    pct = min(100.0, done * 100.0 / total)
                    mb_d = done / (1024 * 1024)
                    mb_t = total / (1024 * 1024)
                    self.after(0, lambda p=pct: self._progress_vars[tool].set(p))
                    self.after(0, lambda d=mb_d, t=mb_t:
                               self._status_vars[tool].set(f"{d:.1f} / {t:.1f} MB"))
                else:
                    mb_d = done / (1024 * 1024)
                    self.after(0, lambda d=mb_d:
                               self._status_vars[tool].set(f"{d:.1f} MB downloaded"))

            try:
                path = tool_downloader.download_and_install(tool, _progress)
                results[tool] = path
                self.after(0, lambda: self._progress_vars[tool].set(100.0))
                self.after(0, lambda: self._status_vars[tool].set("✓ Installed"))
                self.after(0, lambda p=path: self._path_vars[tool].set(p))
            except Exception as exc:
                errors[tool] = str(exc)
                self.after(0, lambda: self._status_vars[tool].set("✗ Failed"))

            remaining[0] -= 1
            if remaining[0] == 0:
                self.after(600, _all_done)

        for tool in self._missing:
            threading.Thread(target=_worker, args=(tool,), daemon=True).start()


# ── Public entry point ────────────────────────────────────────────────────────

def check_and_prompt(root: tk.Tk, app) -> None:
    """
    Run at startup. If either tool is missing, show the setup dialog and update the app's path vars + saved settings once the user resolves it.
    """
    missing: List[str] = []
    if not _fdb.find_filedb():
        missing.append("FileDBReader")
    if not rda_handler.find_rda_console():
        missing.append("RdaConsole")

    if not missing:
        return

    def _on_resolved(paths: Dict[str, str]):
        if paths.get("FileDBReader"):
            app._fdb_path_var.set(paths["FileDBReader"])
        if paths.get("RdaConsole"):
            app._rda_path_var.set(paths["RdaConsole"])
        app._save_settings()

    ToolSetupDialog(root, missing, _on_resolved)
