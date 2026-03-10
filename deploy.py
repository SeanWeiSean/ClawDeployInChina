#!/usr/bin/env python3
"""
OpenClaw Deployer — One-click installer
=========================================
Clean minimal UI: one button to install, one to cancel.
All configuration is read from .env + defaults.
"""

import os
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from deployer.config import DeployerConfig
from deployer.logger import DeployerLogger
from deployer.windows_setup import WindowsSetup, DEFAULT_NODE_DIR

# ═══════════════════════════════════════════════════════════════
# Colour palette  (light, flat, clean)
# ═══════════════════════════════════════════════════════════════
BG           = "#ffffff"
BG_CARD      = "#f7f8fa"
FG           = "#222222"
FG_DIM       = "#999999"
ACCENT       = "#4a90d9"
ACCENT_HOVER = "#3a7bc8"
SUCCESS      = "#34c759"
ERROR        = "#ff3b30"
PROGRESS_BG  = "#e8e8e8"
BTN_CANCEL   = "#e0e0e0"


# ═══════════════════════════════════════════════════════════════
# Main Application
# ═══════════════════════════════════════════════════════════════
class DeployerApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("OpenClaw Installer")
        self.configure(bg=BG)
        self.geometry("480x400")
        self.resizable(False, False)

        self._set_icon()

        self.config = DeployerConfig()
        self.logger = DeployerLogger()
        self._running = False
        self._failed = False

        self._build_ui()

    # ───────────────────── UI ─────────────────────

    def _build_ui(self):
        # Center everything vertically
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = tk.Frame(self, bg=BG)
        container.grid(row=0, column=0)

        # Logo / Title
        tk.Label(container, text="🦞", font=("Segoe UI Emoji", 48),
                 bg=BG, fg=FG).pack(pady=(0, 4))

        tk.Label(container, text="OpenClaw", font=("Segoe UI", 24, "bold"),
                 bg=BG, fg=FG).pack()

        self._subtitle = tk.Label(container, text="一键安装 AI 助手到您的电脑",
                                   font=("Segoe UI", 11), bg=BG, fg=FG_DIM)
        self._subtitle.pack(pady=(2, 16))

        # Mirror selector
        mirror_frame = tk.Frame(container, bg=BG)
        mirror_frame.pack(pady=(0, 16))

        tk.Label(mirror_frame, text="npm 镜像源", font=("Segoe UI", 10),
                 bg=BG, fg=FG_DIM).pack(side="left", padx=(0, 8))

        self._mirror_var = tk.StringVar(value="npmmirror")
        mirror_menu = ttk.Combobox(
            mirror_frame, textvariable=self._mirror_var,
            values=["npmmirror (淘宝)", "tencent (腾讯)"],
            state="readonly", width=18, font=("Segoe UI", 10))
        mirror_menu.current(0)
        mirror_menu.pack(side="left")

        # Progress area (hidden initially)
        self._progress_frame = tk.Frame(container, bg=BG)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Flat.Horizontal.TProgressbar",
                        troughcolor=PROGRESS_BG, background=ACCENT,
                        thickness=6, borderwidth=0)

        self._progress = ttk.Progressbar(
            self._progress_frame, length=320, mode="determinate",
            maximum=100, style="Flat.Horizontal.TProgressbar")
        self._progress.pack(pady=(0, 8))

        self._status_label = tk.Label(
            self._progress_frame, text="准备中…",
            font=("Segoe UI", 10), bg=BG, fg=FG_DIM)
        self._status_label.pack()

        # Buttons
        btn_frame = tk.Frame(container, bg=BG)
        btn_frame.pack(pady=(0, 8))

        self._install_btn = tk.Button(
            btn_frame, text="确认安装", command=self._on_install,
            bg=ACCENT, fg="#ffffff", activebackground=ACCENT_HOVER,
            activeforeground="#ffffff",
            font=("Segoe UI", 13, "bold"), bd=0,
            padx=36, pady=10, cursor="hand2", relief="flat")
        self._install_btn.pack(side="left", padx=8)

        self._cancel_btn = tk.Button(
            btn_frame, text="取消", command=self._on_cancel,
            bg=BTN_CANCEL, fg=FG, activebackground="#d0d0d0",
            font=("Segoe UI", 13), bd=0,
            padx=36, pady=10, cursor="hand2", relief="flat")
        self._cancel_btn.pack(side="left", padx=8)

    # ───────────────────── Actions ─────────────────────

    def _on_install(self):
        if self._running:
            return
        self._running = True
        self._failed = False
        self._install_btn.config(state="disabled", bg="#b0b0b0")
        self._subtitle.config(text="正在安装，请稍候…")
        self._progress_frame.pack(pady=(0, 20))
        self._progress["value"] = 0
        self._status_label.config(text="准备中…", fg=FG_DIM)

        # Pass selected mirror to config
        mirror_sel = self._mirror_var.get()
        if "tencent" in mirror_sel.lower():
            self.config.set("npm.registry", "http://mirrors.cloud.tencent.com/npm/")
        else:
            self.config.set("npm.registry", "https://registry.npmmirror.com")

        threading.Thread(target=self._install_thread, daemon=True).start()

    def _on_cancel(self):
        if self._running:
            self._running = False
            self._status_label.config(text="正在取消…", fg=FG_DIM)
        else:
            self.destroy()

    # ───────────────────── Install thread ─────────────────────

    def _set_progress(self, pct: int, text: str):
        def _do():
            self._progress["value"] = pct
            self._status_label.config(text=text, fg=FG_DIM)
        self.after(0, _do)

    def _finish_ok(self):
        def _do():
            self._progress["value"] = 100
            self._status_label.config(text="✓  安装完成！", fg=SUCCESS)
            self._subtitle.config(text="OpenClaw 已就绪，浏览器即将打开")
            self._install_btn.config(state="normal", text="完成", bg=SUCCESS,
                                      command=self.destroy)
            self._cancel_btn.pack_forget()
        self.after(0, _do)

    def _finish_fail(self, msg: str):
        def _do():
            self._failed = True
            self._status_label.config(text=f"✗  {msg}", fg=ERROR)
            self._subtitle.config(text="安装失败，请检查网络后重试")
            self._install_btn.config(state="normal", text="重试", bg=ACCENT,
                                      command=self._on_install)
        self.after(0, _do)

    def _install_thread(self):
        log = self.logger
        ws = WindowsSetup(self.config, log)

        steps = [
            (5,  "检查 Git…",           ws.ensure_git),
            (15, "检查 Node.js…",       ws.check_node_windows),
            (30, "安装 Node.js…",       ws.install_node_windows),
            (40, "配置 npm 镜像…",      ws.setup_npm_mirror),
            (55, "安装 OpenClaw…",      ws.install_openclaw_windows),
            (65, "配置系统 PATH…",      ws.add_to_path),
            (75, "写入配置文件…",       ws.write_config),
            (82, "安装网关服务…",       ws.run_onboard),
            (90, "启动网关…",           ws.start_gateway),
            (95, "创建桌面快捷方式…",   ws.create_desktop_shortcut),
            (97, "验证安装…",           self._verify),
        ]

        # Pre-step: execution policy
        try:
            ws.ensure_execution_policy()
        except Exception:
            pass
        try:
            ws._configure_git_https()
        except Exception:
            pass

        node_ok = False
        for pct, label, fn in steps:
            if not self._running:
                self._set_progress(pct, "已取消")
                self.after(0, lambda: self._finish_fail("用户取消安装"))
                self._running = False
                return

            self._set_progress(pct, label)

            # Skip node install if already present
            if fn == ws.install_node_windows and node_ok:
                continue
            # Skip openclaw install if already present
            if fn == ws.install_openclaw_windows:
                try:
                    if ws.check_openclaw_windows():
                        continue
                except Exception:
                    pass

            try:
                result = fn()
                # Track node check result
                if fn == ws.check_node_windows:
                    node_ok = bool(result)
                    continue  # Don't fail if node not found — we'll install next

                if not result and fn not in (ws.check_node_windows, ws.run_onboard):
                    self._finish_fail(label.replace("…", "") + " 失败")
                    self._running = False
                    return
            except Exception as e:
                log.error(f"{label} exception: {e}")
                if fn not in (ws.check_node_windows, ws.run_onboard):
                    self._finish_fail(label.replace("…", "") + " 失败")
                    self._running = False
                    return

        self._running = False
        self._finish_ok()

    def _verify(self) -> bool:
        cmd = self._find_openclaw_cmd()
        if not cmd:
            return False
        env = os.environ.copy()
        env["PATH"] = str(DEFAULT_NODE_DIR) + os.pathsep + env.get("PATH", "")
        api_key = self.config.get("model.api_key", "")
        if api_key:
            env["LITELLM_API_KEY"] = api_key
        try:
            r = subprocess.run(
                cmd + ["--version"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=15, env=env,
            )
            return r.returncode == 0 and bool(r.stdout.strip())
        except Exception:
            return False

    # ───────────────────── Helpers ─────────────────────

    def _find_openclaw_cmd(self) -> list[str] | None:
        managed = DEFAULT_NODE_DIR / "openclaw.cmd"
        if managed.exists():
            return [str(managed)]
        managed2 = DEFAULT_NODE_DIR / "openclaw"
        if managed2.exists():
            return [str(managed2)]
        found = shutil.which("openclaw")
        if found:
            return [found]
        npm_prefix = Path.home() / "AppData" / "Roaming" / "npm"
        for name in ("openclaw.cmd", "openclaw"):
            p = npm_prefix / name
            if p.exists():
                return [str(p)]
        return None

    def _set_icon(self):
        import sys
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


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════
def _ensure_admin():
    import ctypes, sys, os
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False
    if is_admin:
        return
    exe = sys.executable
    script = os.path.abspath(sys.argv[0])
    cwd = os.path.dirname(script)
    params = f'"{script}"'
    if sys.argv[1:]:
        params += " " + " ".join(f'"{a}"' for a in sys.argv[1:])
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, cwd, 1)
    if ret > 32:
        sys.exit(0)


if __name__ == "__main__":
    app = DeployerApp()
    app.mainloop()
