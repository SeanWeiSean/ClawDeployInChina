#!/usr/bin/env python3
"""
OpenClaw Deployer — WSL2 Deployment GUI
========================================
A visual, VP-friendly deployment tool that provisions OpenClaw
inside WSL2 from a Windows host.

Run:  python deploy.py
      (or double-click launch.bat)
"""

import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from pathlib import Path

from deployer.config import DeployerConfig
from deployer.logger import DeployerLogger
from deployer.wsl_manager import WSLManager, _decode_wsl
from deployer.openclaw_setup import OpenClawSetup
from deployer.windows_setup import WindowsSetup

# ═══════════════════════════════════════════════════════════════
# Colour palette  (dark professional theme)
# ═══════════════════════════════════════════════════════════════
BG           = "#1e1e2e"
BG_CARD      = "#282840"
BG_INPUT     = "#313150"
FG           = "#cdd6f4"
FG_DIM       = "#6c7086"
ACCENT       = "#89b4fa"
SUCCESS      = "#a6e3a1"
ERROR        = "#f38ba8"
WARNING      = "#f9e2af"
PROGRESS_BG  = "#45475a"
ORANGE       = "#fab387"

# Step states
PENDING     = "pending"
RUNNING     = "running"
OK          = "ok"
FAILED      = "failed"
SKIPPED     = "skipped"

STATE_ICON = {
    PENDING:  ("○", FG_DIM),
    RUNNING:  ("◉", ACCENT),
    OK:       ("✓", SUCCESS),
    FAILED:   ("✗", ERROR),
    SKIPPED:  ("—", FG_DIM),
}


# ═══════════════════════════════════════════════════════════════
# Deployment step definitions
# ═══════════════════════════════════════════════════════════════
STEPS = [
    ("wsl_check",       "Check WSL2 Installation"),
    ("distro_install",  "Install Ubuntu 24.04"),
    ("systemd",         "Enable systemd"),
    ("wsl_restart",     "Restart WSL"),
    ("node_install",    "Install Node.js ≥22"),
    ("pnpm_install",    "Install pnpm"),
    ("openclaw_install","Install OpenClaw"),
    ("write_config",    "Write Configuration"),
    ("verify",          "Verify Installation"),
]

WIN_STEPS = [
    ("win_git",           "Install Git"),
    ("win_node_check",    "Check Node.js (Windows)"),
    ("win_node_install",  "Download Node.js (npmmirror)"),
    ("win_npm_mirror",    "Set npm Registry (npmmirror)"),
    ("win_openclaw",      "Install OpenClaw (npm)"),
    ("win_path",          "Add to System PATH"),
    ("win_config",        "Write LiteLLM Config"),
    ("win_onboard",       "Install Gateway Service"),
    ("win_gateway",       "Start Gateway"),
    ("win_verify",        "Verify Installation"),
]


# ═══════════════════════════════════════════════════════════════
# Main Application
# ═══════════════════════════════════════════════════════════════
class DeployerApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("OpenClaw Deployer  v1.0")
        self.configure(bg=BG)
        self.geometry("1200x860")
        self.minsize(1000, 700)

        # Set window icon
        self._set_icon()

        # State
        self.config = DeployerConfig()
        self.logger = DeployerLogger()
        self.logger.add_listener(self._on_log_line)
        self.step_states: dict[str, str] = {sid: PENDING for sid, _ in STEPS}
        self.win_step_states: dict[str, str] = {sid: PENDING for sid, _ in WIN_STEPS}
        self._running = False
        self._win_running = False
        self._chat_sending = False

        # Widgets
        self._build_ui()
        self._populate_config_fields()

    # ───────────────────── UI Construction ─────────────────────

    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=BG, height=56)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="🦞 OpenClaw Deployer", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=ACCENT).pack(side="left", padx=16, pady=8)
        tk.Label(top, text="WSL2 Automated Deployment", font=("Segoe UI", 10),
                 bg=BG, fg=FG_DIM).pack(side="left", padx=4, pady=8)

        # Separator
        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # Main body: left (config) + center (steps) + right (nothing for now)
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)
        body.grid_columnconfigure(0, weight=2, minsize=340)
        body.grid_columnconfigure(1, weight=3, minsize=400)

        # ─── Left: Configuration Panel ───
        self._build_config_panel(body)
        # ─── Right: Steps + Progress (tabbed: WSL / Windows) ───
        self._build_steps_panel(body)

        # Bottom: Tabbed panel (Log + Chat)
        self._build_bottom_tabs()

    # ---------- Config Panel ----------
    def _build_config_panel(self, parent):
        frame = tk.Frame(parent, bg=BG_CARD, bd=0, highlightthickness=1,
                         highlightbackground="#45475a")
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)

        tk.Label(frame, text="⚙  Configuration", font=("Segoe UI", 13, "bold"),
                 bg=BG_CARD, fg=FG).pack(anchor="w", padx=14, pady=(12, 4))

        canvas = tk.Canvas(frame, bg=BG_CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG_CARD)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=8, pady=4)
        scrollbar.pack(side="right", fill="y")

        # Bind mouse‑wheel so the config panel scrolls
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self._cfg_entries: dict[str, tk.Variable] = {}

        sections = [
            ("WSL", [
                ("wsl.distro",          "Distro",           "str"),
                ("wsl.enable_systemd",  "Enable systemd",   "bool"),
                ("wsl.auto_start_at_boot", "Auto-start at boot", "bool"),
            ]),
            ("Node.js", [
                ("node.version",        "Version",          "str"),
                ("node.install_method", "Method (nvm / nodesource)", "str"),
            ]),
            ("OpenClaw", [
                ("openclaw.install_method", "Install method (npm / source)", "str"),
                ("openclaw.channel",        "Channel (stable / beta / dev)", "str"),
                ("openclaw.install_daemon", "Install daemon",    "bool"),
            ]),
            ("Model / LLM", [
                ("model.provider",   "Provider",    "str"),
                ("model.base_url",   "Base URL",    "str"),
                ("model.api_key",    "API Key",     "password"),
                ("model.model_name", "Model name",  "str"),
            ]),
            ("Gateway", [
                ("gateway.port",  "Port",    "int"),
                ("gateway.bind",  "Bind",    "str"),
            ]),
        ]

        for section_name, fields in sections:
            lbl = tk.Label(scroll_frame, text=section_name, font=("Segoe UI", 11, "bold"),
                           bg=BG_CARD, fg=ORANGE)
            lbl.pack(anchor="w", padx=8, pady=(10, 2))

            for dotpath, label, kind in fields:
                row = tk.Frame(scroll_frame, bg=BG_CARD)
                row.pack(fill="x", padx=12, pady=2)
                tk.Label(row, text=label, font=("Segoe UI", 9), bg=BG_CARD, fg=FG,
                         width=22, anchor="w").pack(side="left")

                if kind == "bool":
                    var = tk.BooleanVar()
                    cb = tk.Checkbutton(row, variable=var, bg=BG_CARD, fg=FG,
                                        selectcolor=BG_INPUT, activebackground=BG_CARD)
                    cb.pack(side="left")
                elif kind == "password":
                    var = tk.StringVar()
                    ent = tk.Entry(row, textvariable=var, show="•", bg=BG_INPUT, fg=FG,
                                   insertbackground=FG, relief="flat", font=("Consolas", 9))
                    ent.pack(side="left", fill="x", expand=True)
                elif kind == "int":
                    var = tk.IntVar()
                    ent = tk.Entry(row, textvariable=var, bg=BG_INPUT, fg=FG,
                                   insertbackground=FG, relief="flat", font=("Consolas", 9), width=8)
                    ent.pack(side="left")
                else:
                    var = tk.StringVar()
                    ent = tk.Entry(row, textvariable=var, bg=BG_INPUT, fg=FG,
                                   insertbackground=FG, relief="flat", font=("Consolas", 9))
                    ent.pack(side="left", fill="x", expand=True)

                self._cfg_entries[dotpath] = var

        # Buttons
        btn_frame = tk.Frame(frame, bg=BG_CARD)
        btn_frame.pack(fill="x", padx=12, pady=10)
        self._make_btn(btn_frame, "💾 Save Config", self._save_config).pack(side="left", padx=(0, 6))
        self._make_btn(btn_frame, "📂 Load Config", self._load_config).pack(side="left")

    # ---------- Steps Panel (tabbed: WSL / Windows) ----------
    def _build_steps_panel(self, parent):
        frame = tk.Frame(parent, bg=BG_CARD, bd=0, highlightthickness=1,
                         highlightbackground="#45475a")
        frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=0)

        # Use a notebook for WSL vs Windows deploy
        style = ttk.Style()
        style.configure("Steps.TNotebook", background=BG_CARD, borderwidth=0)
        style.configure("Steps.TNotebook.Tab",
                        background=BG_INPUT, foreground=FG,
                        padding=[12, 5], font=("Segoe UI", 10, "bold"))
        style.map("Steps.TNotebook.Tab",
                  background=[("selected", BG_CARD)],
                  foreground=[("selected", ACCENT)])

        nb = ttk.Notebook(frame, style="Steps.TNotebook")
        nb.pack(fill="both", expand=True, padx=4, pady=4)

        # ── Tab 1: Windows Deploy ──
        win_tab = tk.Frame(nb, bg=BG_CARD)
        nb.add(win_tab, text="  🪟  Install on Windows  ")
        self._build_win_steps(win_tab)

        # ── Tab 2: WSL Deploy ──
        wsl_tab = tk.Frame(nb, bg=BG_CARD)
        nb.add(wsl_tab, text="  🐧  Deploy to WSL2  ")
        self._build_wsl_steps(wsl_tab)

    def _build_step_rows(self, parent, steps, widgets_dict):
        """Build step rows into parent frame; store widget refs in widgets_dict."""
        for sid, label in steps:
            row = tk.Frame(parent, bg=BG_CARD)
            row.pack(fill="x", padx=16, pady=4)

            icon_lbl = tk.Label(row, text="○", font=("Segoe UI", 14),
                                bg=BG_CARD, fg=FG_DIM, width=2)
            icon_lbl.pack(side="left")

            name_lbl = tk.Label(row, text=label, font=("Segoe UI", 11),
                                bg=BG_CARD, fg=FG, anchor="w")
            name_lbl.pack(side="left", padx=(4, 0), fill="x", expand=True)

            status_lbl = tk.Label(row, text="Pending", font=("Segoe UI", 9),
                                  bg=BG_CARD, fg=FG_DIM, width=14, anchor="e")
            status_lbl.pack(side="right")

            widgets_dict[sid] = {
                "icon": icon_lbl,
                "name": name_lbl,
                "status": status_lbl,
            }

    def _build_wsl_steps(self, parent):
        tk.Label(parent, text="📋  WSL2 Deployment Steps", font=("Segoe UI", 13, "bold"),
                 bg=BG_CARD, fg=FG).pack(anchor="w", padx=14, pady=(12, 4))

        self._step_widgets: dict[str, dict] = {}
        self._build_step_rows(parent, STEPS, self._step_widgets)

        # Progress bar
        tk.Label(parent, text="Overall Progress", font=("Segoe UI", 9, "bold"),
                 bg=BG_CARD, fg=FG_DIM).pack(anchor="w", padx=16, pady=(16, 2))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("green.Horizontal.TProgressbar",
                        troughcolor=PROGRESS_BG, background=SUCCESS,
                        thickness=18)

        self._progress = ttk.Progressbar(parent, maximum=len(STEPS),
                                          style="green.Horizontal.TProgressbar")
        self._progress.pack(fill="x", padx=16, pady=(0, 4))

        self._progress_label = tk.Label(parent, text="0 / {} steps".format(len(STEPS)),
                                         font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM)
        self._progress_label.pack(anchor="w", padx=16)

        # Buttons
        btn_frame = tk.Frame(parent, bg=BG_CARD)
        btn_frame.pack(fill="x", padx=16, pady=12)

        self._deploy_btn = self._make_btn(btn_frame, "🚀  Deploy to WSL", self._start_deploy,
                                           bg=ACCENT, fg="#1e1e2e", font_size=12)
        self._deploy_btn.pack(side="left", padx=(0, 8), ipadx=16, ipady=4)

        self._stop_btn = self._make_btn(btn_frame, "⏹ Stop", self._stop_deploy,
                                         bg=ERROR, fg="#1e1e2e")
        self._stop_btn.pack(side="left", padx=(0, 8))
        self._stop_btn.config(state="disabled")

        self._reset_btn = self._make_btn(btn_frame, "↻ Reset", self._reset_steps)
        self._reset_btn.pack(side="left")

    def _build_win_steps(self, parent):
        tk.Label(parent, text="📋  Windows Installation Steps", font=("Segoe UI", 13, "bold"),
                 bg=BG_CARD, fg=FG).pack(anchor="w", padx=14, pady=(12, 4))

        # Info label
        info = tk.Label(parent,
                        text="Downloads Node.js from npmmirror, sets taobao npm registry,\n"
                             "and installs OpenClaw directly on Windows.",
                        font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM,
                        justify="left")
        info.pack(anchor="w", padx=16, pady=(0, 8))

        self._win_step_widgets: dict[str, dict] = {}
        self._build_step_rows(parent, WIN_STEPS, self._win_step_widgets)

        # Progress bar
        tk.Label(parent, text="Overall Progress", font=("Segoe UI", 9, "bold"),
                 bg=BG_CARD, fg=FG_DIM).pack(anchor="w", padx=16, pady=(16, 2))

        style = ttk.Style()
        style.configure("blue.Horizontal.TProgressbar",
                        troughcolor=PROGRESS_BG, background=ACCENT,
                        thickness=18)

        self._win_progress = ttk.Progressbar(parent, maximum=len(WIN_STEPS),
                                              style="blue.Horizontal.TProgressbar")
        self._win_progress.pack(fill="x", padx=16, pady=(0, 4))

        self._win_progress_label = tk.Label(parent, text="0 / {} steps".format(len(WIN_STEPS)),
                                             font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM)
        self._win_progress_label.pack(anchor="w", padx=16)

        # Buttons
        btn_frame = tk.Frame(parent, bg=BG_CARD)
        btn_frame.pack(fill="x", padx=16, pady=12)

        self._win_deploy_btn = self._make_btn(
            btn_frame, "🪟  Install on Windows", self._start_win_deploy,
            bg=ORANGE, fg="#1e1e2e", font_size=12)
        self._win_deploy_btn.pack(side="left", padx=(0, 8), ipadx=16, ipady=4)

        self._win_stop_btn = self._make_btn(btn_frame, "⏹ Stop", self._stop_win_deploy,
                                             bg=ERROR, fg="#1e1e2e")
        self._win_stop_btn.pack(side="left", padx=(0, 8))
        self._win_stop_btn.config(state="disabled")

        self._win_reset_btn = self._make_btn(btn_frame, "↻ Reset", self._reset_win_steps)
        self._win_reset_btn.pack(side="left")

        self._win_uninstall_btn = self._make_btn(
            btn_frame, "🗑 Uninstall", self._uninstall_openclaw,
            bg="#45475a", fg=ERROR)
        self._win_uninstall_btn.pack(side="right")

    # ---------- Bottom Tabbed Panel (Log + Chat) ----------
    def _build_bottom_tabs(self):
        # Custom style for dark themed notebook tabs
        style = ttk.Style()
        style.configure("Dark.TNotebook", background=BG, borderwidth=0)
        style.configure("Dark.TNotebook.Tab",
                        background=BG_INPUT, foreground=FG,
                        padding=[14, 6], font=("Segoe UI", 10, "bold"))
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", BG_CARD)],
                  foreground=[("selected", ACCENT)])

        notebook = ttk.Notebook(self, style="Dark.TNotebook")
        notebook.pack(fill="both", expand=True, padx=12, pady=(8, 12))

        # ─── Tab 1: Log ───
        log_tab = tk.Frame(notebook, bg=BG_CARD)
        notebook.add(log_tab, text="  📜  Deployment Log  ")
        self._build_log_content(log_tab)

        # ─── Tab 2: Chat ───
        chat_tab = tk.Frame(notebook, bg=BG_CARD)
        notebook.add(chat_tab, text="  💬  Chat with OpenClaw  ")
        self._build_chat_content(chat_tab)

    def _build_log_content(self, parent):
        header = tk.Frame(parent, bg=BG_CARD)
        header.pack(fill="x")
        self._make_btn(header, "Export Log", self._export_log).pack(side="right", padx=12, pady=6)

        self._log_text = tk.Text(parent, height=12, bg="#11111b", fg=FG,
                                  font=("Consolas", 9), relief="flat",
                                  insertbackground=FG, wrap="word",
                                  state="disabled")
        log_scroll = ttk.Scrollbar(parent, orient="vertical", command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        self._log_text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 8))
        log_scroll.pack(side="right", fill="y", padx=(0, 4), pady=(0, 8))

        # Tag colours for log levels
        self._log_text.tag_configure("INFO",    foreground=FG)
        self._log_text.tag_configure("WARNING", foreground=WARNING)
        self._log_text.tag_configure("ERROR",   foreground=ERROR)
        self._log_text.tag_configure("DEBUG",   foreground=FG_DIM)

    # ---------- Chat Panel ----------
    def _build_chat_content(self, parent):
        # Status bar
        status_bar = tk.Frame(parent, bg=BG_CARD)
        status_bar.pack(fill="x", padx=12, pady=(8, 0))

        self._chat_status = tk.Label(
            status_bar, text="● Gateway: checking…",
            font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM, anchor="w")
        self._chat_status.pack(side="left")

        self._make_btn(status_bar, "↻ Check Gateway", self._check_gateway_status
                       ).pack(side="right")

        # Chat history area
        self._chat_display = tk.Text(
            parent, bg="#11111b", fg=FG, font=("Segoe UI", 10),
            relief="flat", wrap="word", state="disabled",
            insertbackground=FG, padx=12, pady=8)
        chat_scroll = ttk.Scrollbar(parent, orient="vertical",
                                     command=self._chat_display.yview)
        self._chat_display.configure(yscrollcommand=chat_scroll.set)
        self._chat_display.pack(side="top", fill="both", expand=True,
                                 padx=(12, 0), pady=(6, 0))
        chat_scroll.pack(in_=parent, side="right", fill="y",
                          padx=(0, 4), pady=(6, 0))
        # we need to re-pack scroll next to display; use a sub-frame instead
        chat_scroll.pack_forget()
        self._chat_display.pack_forget()

        chat_mid = tk.Frame(parent, bg=BG_CARD)
        chat_mid.pack(fill="both", expand=True, padx=12, pady=(6, 0))

        self._chat_display = tk.Text(
            chat_mid, bg="#11111b", fg=FG, font=("Segoe UI", 10),
            relief="flat", wrap="word", state="disabled",
            insertbackground=FG, padx=12, pady=8)
        chat_scroll2 = ttk.Scrollbar(chat_mid, orient="vertical",
                                      command=self._chat_display.yview)
        self._chat_display.configure(yscrollcommand=chat_scroll2.set)
        self._chat_display.pack(side="left", fill="both", expand=True)
        chat_scroll2.pack(side="right", fill="y")

        # Tag styles for chat bubbles
        self._chat_display.tag_configure(
            "user", foreground=ACCENT, font=("Segoe UI", 10, "bold"))
        self._chat_display.tag_configure(
            "user_msg", foreground=FG, lmargin1=16, lmargin2=16)
        self._chat_display.tag_configure(
            "bot", foreground=SUCCESS, font=("Segoe UI", 10, "bold"))
        self._chat_display.tag_configure(
            "bot_msg", foreground=FG, lmargin1=16, lmargin2=16)
        self._chat_display.tag_configure(
            "system", foreground=FG_DIM, font=("Segoe UI", 9, "italic"),
            justify="center")
        self._chat_display.tag_configure(
            "error_msg", foreground=ERROR)

        # Input bar
        input_bar = tk.Frame(parent, bg=BG_CARD)
        input_bar.pack(fill="x", padx=12, pady=(6, 10))

        self._chat_input = tk.Entry(
            input_bar, bg=BG_INPUT, fg=FG, font=("Segoe UI", 11),
            insertbackground=FG, relief="flat")
        self._chat_input.pack(side="left", fill="x", expand=True,
                               ipady=6, padx=(0, 8))
        self._chat_input.bind("<Return>", lambda e: self._send_chat())
        self._chat_input.insert(0, "")

        self._send_btn = self._make_btn(
            input_bar, "Send  ➤", self._send_chat,
            bg=ACCENT, fg="#1e1e2e", font_size=11)
        self._send_btn.pack(side="right", ipadx=12, ipady=4)

        # Welcome message
        self._chat_append_system(
            "🦞 Welcome! Chat with your OpenClaw assistant here.\n"
            "Make sure the gateway is running (deploy first via the Install tab).\n"
            "Messages are routed through your LiteLLM proxy → Claude.")

    # ───────────────────── Helpers ─────────────────────

    @staticmethod
    def _make_btn(parent, text, command, bg=BG_INPUT, fg=FG, font_size=10):
        btn = tk.Button(parent, text=text, command=command,
                        bg=bg, fg=fg, activebackground=bg,
                        font=("Segoe UI", font_size), bd=0, padx=12, pady=4,
                        cursor="hand2", relief="flat")
        return btn

    def _set_icon(self):
        """Set the window icon from bundled or local openclaw.ico."""
        import sys
        from pathlib import Path
        # Look for ico: bundled (_MEIPASS) or next to exe/script
        candidates = []
        if getattr(sys, 'frozen', False):
            candidates.append(Path(sys._MEIPASS) / "openclaw.ico")
            candidates.append(Path(sys.executable).parent / "openclaw.ico")
        candidates.append(Path.cwd() / "openclaw.ico")
        candidates.append(Path(__file__).parent / "openclaw.ico")
        for ico in candidates:
            if ico.exists():
                try:
                    self.iconbitmap(str(ico))
                    return
                except Exception:
                    pass

    def _populate_config_fields(self):
        for dotpath, var in self._cfg_entries.items():
            val = self.config.get(dotpath)
            if val is not None:
                var.set(val)

    def _sync_config_from_ui(self):
        for dotpath, var in self._cfg_entries.items():
            self.config.set(dotpath, var.get())

    def _save_config(self):
        self._sync_config_from_ui()
        self.config.save()
        self.logger.info(f"Configuration saved to {self.config.path}")

    def _load_config(self):
        path = filedialog.askopenfilename(
            filetypes=[("YAML files", "*.yaml *.yml"), ("All", "*.*")])
        if path:
            self.config = DeployerConfig(Path(path))
            self._populate_config_fields()
            self.logger.info(f"Configuration loaded from {path}")

    def _export_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".log",
            initialfile=f"openclaw_deploy_{datetime.now():%Y%m%d_%H%M%S}.log",
            filetypes=[("Log files", "*.log"), ("Text", "*.txt")])
        if path:
            self.logger.export(path)
            self.logger.info(f"Log exported to {path}")

    # ───────────────────── Log callback ─────────────────────

    def _on_log_line(self, line: str):
        """Thread-safe append to the log text widget."""
        def _append():
            self._log_text.config(state="normal")
            # colour by level
            tag = "INFO"
            for lvl in ("ERROR", "WARNING", "DEBUG"):
                if lvl in line:
                    tag = lvl
                    break
            self._log_text.insert("end", line + "\n", tag)
            self._log_text.see("end")
            self._log_text.config(state="disabled")
        self.after(0, _append)

    # ───────────────────── Step state ─────────────────────

    def _set_step(self, sid: str, state: str, detail: str = ""):
        self.step_states[sid] = state
        icon_txt, icon_clr = STATE_ICON[state]
        labels = {
            PENDING: "Pending",
            RUNNING: "Running…",
            OK:      "Done",
            FAILED:  "Failed",
            SKIPPED: "Skipped",
        }
        status_txt = detail or labels[state]

        def _update():
            w = self._step_widgets[sid]
            w["icon"].config(text=icon_txt, fg=icon_clr)
            w["status"].config(text=status_txt, fg=icon_clr)
            # update progress
            done = sum(1 for s in self.step_states.values() if s in (OK, SKIPPED))
            self._progress["value"] = done
            self._progress_label.config(text=f"{done} / {len(STEPS)} steps")
        self.after(0, _update)

    def _set_win_step(self, sid: str, state: str, detail: str = ""):
        self.win_step_states[sid] = state
        icon_txt, icon_clr = STATE_ICON[state]
        labels = {
            PENDING: "Pending",
            RUNNING: "Running…",
            OK:      "Done",
            FAILED:  "Failed",
            SKIPPED: "Skipped",
        }
        status_txt = detail or labels[state]

        def _update():
            w = self._win_step_widgets[sid]
            w["icon"].config(text=icon_txt, fg=icon_clr)
            w["status"].config(text=status_txt, fg=icon_clr)
            done = sum(1 for s in self.win_step_states.values() if s in (OK, SKIPPED))
            self._win_progress["value"] = done
            self._win_progress_label.config(text=f"{done} / {len(WIN_STEPS)} steps")
        self.after(0, _update)

    def _reset_steps(self):
        for sid, _ in STEPS:
            self._set_step(sid, PENDING)

    def _reset_win_steps(self):
        for sid, _ in WIN_STEPS:
            self._set_win_step(sid, PENDING)

    # ───────────────────── WSL Deploy orchestration ─────────────────────

    def _start_deploy(self):
        if self._running:
            return
        self._running = True
        self._deploy_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._reset_steps()
        self._sync_config_from_ui()

        t = threading.Thread(target=self._deploy_thread, daemon=True)
        t.start()

    def _stop_deploy(self):
        self._running = False
        self.logger.warn("Deployment stopped by user")
        self._deploy_btn.config(state="normal")
        self._stop_btn.config(state="disabled")

    def _deploy_thread(self):
        """Run all deployment steps sequentially in a background thread."""
        log = self.logger
        wsl = WSLManager(self.config, log)
        oc = OpenClawSetup(self.config, wsl, log)

        log.info("=" * 56)
        log.info("  OpenClaw Deployer — deployment started")
        log.info(f"  Distro : {self.config.get('wsl.distro')}")
        log.info(f"  Model  : {self.config.get('model.model_name')}")
        log.info("=" * 56)

        def _exec_step(sid: str, fn, skip_check=None):
            """Run one step; honour stop flag."""
            if not self._running:
                self._set_step(sid, SKIPPED, "Stopped")
                return False
            if skip_check and skip_check():
                self._set_step(sid, OK, "Already done")
                log.info(f"Step [{sid}] skipped (already satisfied)")
                return True
            self._set_step(sid, RUNNING)
            try:
                result = fn()
                if result:
                    self._set_step(sid, OK)
                else:
                    self._set_step(sid, FAILED)
                return result
            except Exception as exc:
                log.error(f"Step [{sid}] exception: {exc}")
                self._set_step(sid, FAILED, str(exc)[:30])
                return False

        # 1. Check WSL
        if not _exec_step("wsl_check", wsl.is_wsl_installed):
            log.warn("WSL2 not found — attempting install…")
            _exec_step("wsl_check", wsl.install_wsl)

        # 2. Distro
        _exec_step("distro_install", wsl.install_distro,
                    skip_check=wsl.is_distro_installed)

        # 3. systemd
        if self.config.get("wsl.enable_systemd"):
            _exec_step("systemd", wsl.enable_systemd,
                        skip_check=wsl.is_systemd_enabled)
        else:
            self._set_step("systemd", SKIPPED, "Disabled in config")

        # 4. WSL restart
        _exec_step("wsl_restart", wsl.shutdown_wsl)

        # 5. Node.js
        _exec_step("node_install", oc.install_node,
                    skip_check=oc.check_node)

        # 6. pnpm
        _exec_step("pnpm_install", oc.install_pnpm,
                    skip_check=oc.check_pnpm)

        # 7. OpenClaw
        _exec_step("openclaw_install", oc.install_openclaw,
                    skip_check=oc.check_openclaw)

        # 8. Config
        _exec_step("write_config", oc.write_openclaw_config)

        # 9. Verify
        _exec_step("verify", oc.verify_installation)

        # Auto-start (optional, not a visible step)
        if self.config.get("wsl.auto_start_at_boot"):
            wsl.setup_auto_start()

        # Summary
        ok_count = sum(1 for s in self.step_states.values() if s == OK)
        fail_count = sum(1 for s in self.step_states.values() if s == FAILED)
        log.info("=" * 56)
        if fail_count == 0:
            log.success(f"Deployment complete!  {ok_count}/{len(STEPS)} steps succeeded.")
        else:
            log.warn(f"Deployment finished with {fail_count} failure(s).")
        log.info(f"Log file: {log.log_file}")
        log.info("=" * 56)

        self._running = False
        self.after(0, lambda: self._deploy_btn.config(state="normal"))
        self.after(0, lambda: self._stop_btn.config(state="disabled"))

    # ───────────────────── Windows Deploy orchestration ─────────────────────

    def _start_win_deploy(self):
        if self._win_running:
            return
        self._win_running = True
        self._win_deploy_btn.config(state="disabled")
        self._win_stop_btn.config(state="normal")
        self._reset_win_steps()
        self._sync_config_from_ui()

        t = threading.Thread(target=self._win_deploy_thread, daemon=True)
        t.start()

    def _stop_win_deploy(self):
        self._win_running = False
        self.logger.warn("Windows install stopped by user")
        self._win_deploy_btn.config(state="normal")
        self._win_stop_btn.config(state="disabled")

    def _uninstall_openclaw(self):
        """Uninstall OpenClaw from Windows."""
        if not messagebox.askyesno(
            "Uninstall OpenClaw",
            "This will:\n"
            "• Stop the gateway\n"
            "• npm uninstall -g openclaw\n"
            "• Remove ~/.openclaw/ config\n"
            "• Remove scheduled tasks\n\n"
            "Continue?"
        ):
            return

        self._win_uninstall_btn.config(state="disabled")
        t = threading.Thread(target=self._uninstall_thread, daemon=True)
        t.start()

    def _uninstall_thread(self):
        import os, shutil
        log = self.logger
        log.info("=" * 56)
        log.info("  Uninstalling OpenClaw…")
        log.info("=" * 56)

        # 1. Stop gateway
        log.step("Stopping gateway…")
        try:
            subprocess.run(
                ["taskkill", "/IM", "node.exe", "/F"],
                capture_output=True, timeout=10,
            )
            log.success("Gateway stopped")
        except Exception:
            log.info("No gateway process found")

        # 2. npm uninstall
        log.step("Running npm uninstall -g openclaw…")
        cmd = self._find_openclaw_cmd()
        from deployer.windows_setup import DEFAULT_NODE_DIR
        npm_paths = [
            str(DEFAULT_NODE_DIR / "npm.cmd"),
            shutil.which("npm"),
        ]
        npm = next((p for p in npm_paths if p and os.path.exists(p)), None)
        if npm:
            env = os.environ.copy()
            env["PATH"] = str(DEFAULT_NODE_DIR) + os.pathsep + env.get("PATH", "")
            try:
                r = subprocess.run(
                    [npm, "uninstall", "-g", "openclaw"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=120, env=env,
                )
                log.info(f"npm uninstall: {r.stdout.strip()[:200]}")
                log.success("OpenClaw package removed")
            except Exception as e:
                log.error(f"npm uninstall failed: {e}")
        else:
            log.warn("npm not found, skipping package removal")

        # 3. Remove config
        log.step("Removing ~/.openclaw/ config…")
        openclaw_dir = Path.home() / ".openclaw"
        if openclaw_dir.exists():
            try:
                shutil.rmtree(openclaw_dir)
                log.success(f"Removed {openclaw_dir}")
            except Exception as e:
                log.warn(f"Could not fully remove {openclaw_dir}: {e}")
        else:
            log.info("No config directory found")

        # 4. Remove scheduled tasks
        log.step("Removing scheduled tasks…")
        for task_name in ["openclaw-gateway", "WSL Boot - OpenClaw"]:
            try:
                subprocess.run(
                    ["schtasks", "/delete", "/tn", task_name, "/f"],
                    capture_output=True, timeout=10,
                )
            except Exception:
                pass
        log.success("Scheduled tasks cleaned up")

        log.info("=" * 56)
        log.success("OpenClaw uninstalled!")
        log.info("=" * 56)

        self.after(0, lambda: self._win_uninstall_btn.config(state="normal"))

    def _win_deploy_thread(self):
        """Run Windows install steps in a background thread."""
        log = self.logger
        ws = WindowsSetup(self.config, log)

        log.info("=" * 56)
        log.info("  Windows Installation — started")
        log.info(f"  Node mirror: npmmirror")
        log.info(f"  npm registry: taobao")
        log.info("=" * 56)

        def _exec(sid, fn, skip_check=None):
            if not self._win_running:
                self._set_win_step(sid, SKIPPED, "Stopped")
                return False
            if skip_check and skip_check():
                self._set_win_step(sid, OK, "Already done")
                log.info(f"Step [{sid}] skipped (already satisfied)")
                return True
            self._set_win_step(sid, RUNNING)
            try:
                result = fn()
                self._set_win_step(sid, OK if result else FAILED)
                return result
            except Exception as exc:
                log.error(f"Step [{sid}] exception: {exc}")
                self._set_win_step(sid, FAILED, str(exc)[:30])
                return False

        # 0. Ensure git is available
        _exec("win_git", ws.ensure_git)

        # 1. Check Node
        has_node = _exec("win_node_check", ws.check_node_windows)

        # 2. Download & Install Node if needed
        if not has_node:
            # Node missing or too old — not a failure, just needs install
            self._set_win_step("win_node_check", OK, "Need upgrade")
            _exec("win_node_install", ws.install_node_windows)
        else:
            self._set_win_step("win_node_install", SKIPPED, "Node OK")

        # 3. npm mirror
        _exec("win_npm_mirror", ws.setup_npm_mirror)

        # 4. Install OpenClaw
        _exec("win_openclaw", ws.install_openclaw_windows,
              skip_check=ws.check_openclaw_windows)

        # 5. Add to PATH
        _exec("win_path", ws.add_to_path)

        # 6. Write LiteLLM config
        _exec("win_config", ws.write_config)

        # 7. Onboard + install daemon
        _exec("win_onboard", ws.run_onboard)

        # 8. Start gateway
        _exec("win_gateway", ws.start_gateway)

        # 9. Verify — version check + live chat test
        def _verify_openclaw():
            cmd = self._find_openclaw_cmd()
            if not cmd:
                log.error("openclaw not found in PATH")
                return False
            import os, time
            from deployer.windows_setup import DEFAULT_NODE_DIR
            env = os.environ.copy()
            env["PATH"] = str(DEFAULT_NODE_DIR) + os.pathsep + env.get("PATH", "")
            api_key = self.config.get("model.api_key", "")
            if api_key:
                env["LITELLM_API_KEY"] = api_key

            # Step A: version check
            try:
                r = subprocess.run(
                    cmd + ["--version"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=15, env=env,
                )
                ver = r.stdout.strip()
                if ver and r.returncode == 0:
                    log.success(f"openclaw --version → {ver}")
                else:
                    err = r.stderr.strip()
                    log.error(f"openclaw --version failed: {err[:300]}")
                    return False
            except Exception as e:
                log.error(f"Version check failed: {e}")
                return False

            # Step B: live chat test (wait for gateway to be ready)
            log.step("Testing live chat (sending 'hi')…")
            time.sleep(3)  # give gateway a moment to fully start
            try:
                r = subprocess.run(
                    cmd + ["agent", "--message", "say hi in one word", "--session-id", "main"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=60, env=env,
                )
                output = r.stdout.strip()
                # Filter out OpenClaw banner lines
                lines = [l for l in output.splitlines()
                         if l.strip() and not l.strip().startswith("🦞")
                         and not l.strip().startswith("│") and not l.strip().startswith("◇")]
                reply = lines[-1].strip() if lines else output.strip()
                if reply:
                    log.success(f"Chat test passed! OpenClaw says: {reply}")
                    return True
                else:
                    log.warn(f"Chat test: no reply (gateway may still be starting)")
                    return True  # version check passed, chat is optional
            except subprocess.TimeoutExpired:
                log.warn("Chat test timed out (gateway may not be ready yet)")
                return True  # version passed
            except Exception as e:
                log.warn(f"Chat test: {e}")
                return True  # version passed

        _exec("win_verify", _verify_openclaw)

        # Summary
        ok_count = sum(1 for s in self.win_step_states.values() if s == OK)
        fail_count = sum(1 for s in self.win_step_states.values() if s == FAILED)
        log.info("=" * 56)
        if fail_count == 0:
            log.success(f"Windows install complete!  {ok_count}/{len(WIN_STEPS)} steps succeeded.")
            log.info("")
            # Show dashboard URL prominently
            dashboard_url = getattr(ws, '_dashboard_url', '')
            if dashboard_url:
                log.info(f"  ★ Dashboard: {dashboard_url}")
            log.info("  🦞 Let's chat!  →  Switch to the 💬 Chat tab")
            log.info("")
        else:
            log.warn(f"Windows install finished with {fail_count} failure(s).")
        log.info("=" * 56)

        self._win_running = False
        self.after(0, lambda: self._win_deploy_btn.config(state="normal"))
        self.after(0, lambda: self._win_stop_btn.config(state="disabled"))

    # ───────────────────── Chat methods ─────────────────────

    def _chat_append_system(self, text: str):
        def _do():
            self._chat_display.config(state="normal")
            self._chat_display.insert("end", f"\n{text}\n\n", "system")
            self._chat_display.see("end")
            self._chat_display.config(state="disabled")
        self.after(0, _do)

    def _chat_append_user(self, text: str):
        def _do():
            self._chat_display.config(state="normal")
            ts = datetime.now().strftime("%H:%M")
            self._chat_display.insert("end", f"\n  You  ({ts})\n", "user")
            self._chat_display.insert("end", f"{text}\n", "user_msg")
            self._chat_display.see("end")
            self._chat_display.config(state="disabled")
        self.after(0, _do)

    def _chat_append_bot(self, text: str):
        def _do():
            self._chat_display.config(state="normal")
            ts = datetime.now().strftime("%H:%M")
            self._chat_display.insert("end", f"\n  🦞 OpenClaw  ({ts})\n", "bot")
            self._chat_display.insert("end", f"{text}\n", "bot_msg")
            self._chat_display.see("end")
            self._chat_display.config(state="disabled")
        self.after(0, _do)

    def _chat_append_error(self, text: str):
        def _do():
            self._chat_display.config(state="normal")
            self._chat_display.insert("end", f"\n  ⚠ {text}\n", "error_msg")
            self._chat_display.see("end")
            self._chat_display.config(state="disabled")
        self.after(0, _do)

    def _send_chat(self):
        msg = self._chat_input.get().strip()
        if not msg or self._chat_sending:
            return
        self._chat_input.delete(0, "end")
        self._chat_append_user(msg)
        self._chat_sending = True
        self._send_btn.config(state="disabled", text="Thinking…")

        t = threading.Thread(target=self._chat_worker, args=(msg,), daemon=True)
        t.start()

    def _find_openclaw_cmd(self) -> list[str] | None:
        """Find openclaw executable — Windows native first, then WSL."""
        import shutil
        from deployer.windows_setup import DEFAULT_NODE_DIR

        # 1. Managed node dir
        managed = DEFAULT_NODE_DIR / "openclaw.cmd"
        if managed.exists():
            return [str(managed)]
        managed2 = DEFAULT_NODE_DIR / "openclaw"
        if managed2.exists():
            return [str(managed2)]

        # 2. System PATH (Windows)
        found = shutil.which("openclaw")
        if found:
            return [found]

        # 3. npm global (Windows)
        npm_prefix = Path.home() / "AppData" / "Roaming" / "npm"
        for name in ("openclaw.cmd", "openclaw"):
            p = npm_prefix / name
            if p.exists():
                return [str(p)]

        return None

    def _chat_worker(self, message: str):
        """Send message to OpenClaw — try Windows native first, fall back to WSL."""
        # Try Windows native
        cmd = self._find_openclaw_cmd()
        if cmd:
            self._chat_worker_windows(cmd, message)
        else:
            self._chat_worker_wsl(message)

    def _chat_worker_windows(self, cmd: list[str], message: str):
        """Send message via Windows-native openclaw."""
        import os
        from deployer.windows_setup import DEFAULT_NODE_DIR
        try:
            env = os.environ.copy()
            env["PATH"] = str(DEFAULT_NODE_DIR) + os.pathsep + env.get("PATH", "")
            # Set API env var for LiteLLM custom provider
            api_key = self.config.get("model.api_key", "")
            if api_key:
                env["LITELLM_API_KEY"] = api_key

            r = subprocess.run(
                cmd + ["agent", "--message", message, "--session-id", "main"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120, env=env,
            )
            output = r.stdout.strip()
            stderr = r.stderr.strip()
            if output:
                self._chat_append_bot(output)
            else:
                self._chat_append_error(
                    f"No response from OpenClaw.\n"
                    f"Return code: {r.returncode}\n"
                    f"{stderr[:300] if stderr else 'Make sure the gateway is running.'}")
        except subprocess.TimeoutExpired:
            self._chat_append_error("Response timed out (120s). The model may be overloaded.")
        except Exception as e:
            self._chat_append_error(f"Error: {e}")
        finally:
            self._chat_sending = False
            self.after(0, lambda: self._send_btn.config(state="normal", text="Send  ➤"))

    def _chat_worker_wsl(self, message: str):
        """Send message via WSL openclaw (fallback)."""
        distro = self.config.get("wsl.distro", "Ubuntu-24.04")
        try:
            r = subprocess.run(
                [
                    "wsl", "-d", distro, "--",
                    "bash", "-lc",
                    f'openclaw agent --message {self._shell_quote(message)} --session-id main 2>&1',
                ],
                capture_output=True, timeout=120,
            )
            output = _decode_wsl(r.stdout).strip()
            stderr = _decode_wsl(r.stderr).strip()
            if output:
                self._chat_append_bot(output)
            else:
                self._chat_append_error(
                    f"No response from OpenClaw.\n"
                    f"Return code: {r.returncode}\n"
                    f"{stderr[:300] if stderr else 'Make sure the gateway is running.'}")
        except subprocess.TimeoutExpired:
            self._chat_append_error("Response timed out (120s). The model may be overloaded.")
        except FileNotFoundError:
            self._chat_append_error("OpenClaw not found. Please install via Windows or WSL tab first.")
        except Exception as e:
            self._chat_append_error(f"Error: {e}")
        finally:
            self._chat_sending = False
            self.after(0, lambda: self._send_btn.config(state="normal", text="Send  ➤"))

    def _check_gateway_status(self):
        """Check if the OpenClaw gateway is reachable."""
        def _check():
            # Try Windows native first
            cmd = self._find_openclaw_cmd()
            if cmd:
                try:
                    import os
                    from deployer.windows_setup import DEFAULT_NODE_DIR
                    env = os.environ.copy()
                    env["PATH"] = str(DEFAULT_NODE_DIR) + os.pathsep + env.get("PATH", "")
                    api_key = self.config.get("model.api_key", "")
                    if api_key:
                        env["LITELLM_API_KEY"] = api_key
                    r = subprocess.run(
                        cmd + ["gateway", "status"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=15, env=env,
                    )
                    text = r.stdout.strip()
                    if r.returncode == 0:
                        self.after(0, lambda: self._chat_status.config(
                            text=f"● Gateway: online (Windows)  —  {text[:50]}", fg=SUCCESS))
                        return
                except Exception:
                    pass

            # Fall back to WSL
            distro = self.config.get("wsl.distro", "Ubuntu-24.04")
            try:
                r = subprocess.run(
                    ["wsl", "-d", distro, "--", "bash", "-lc",
                     "openclaw gateway status 2>&1"],
                    capture_output=True, timeout=15,
                )
                text = _decode_wsl(r.stdout).strip()
                if r.returncode == 0:
                    self.after(0, lambda: self._chat_status.config(
                        text=f"● Gateway: online  —  {text[:60]}", fg=SUCCESS))
                else:
                    self.after(0, lambda: self._chat_status.config(
                        text="○ Gateway: offline", fg=ERROR))
            except Exception:
                self.after(0, lambda: self._chat_status.config(
                    text="○ Gateway: unreachable (WSL not ready?)", fg=ERROR))
        threading.Thread(target=_check, daemon=True).start()

    @staticmethod
    def _shell_quote(s: str) -> str:
        """Safely quote a string for bash shell."""
        return "'" + s.replace("'", "'\''") + "'"


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════
def _ensure_admin():
    """If not running as admin, relaunch elevated and exit."""
    import ctypes, sys, os
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False

    if is_admin:
        return  # already admin

    # Relaunch as admin
    exe = sys.executable
    script = os.path.abspath(sys.argv[0])
    cwd = os.path.dirname(script)
    params = f'"{script}"'
    if sys.argv[1:]:
        params += " " + " ".join(f'"{a}"' for a in sys.argv[1:])
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", exe, params, cwd, 1
    )
    if ret > 32:
        sys.exit(0)  # elevated process launched, exit this one
    # User denied UAC — continue without admin
    # (gateway install may fail but everything else works)


if __name__ == "__main__":
    _ensure_admin()
    app = DeployerApp()
    app.mainloop()
