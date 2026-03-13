#!/usr/bin/env python3
"""
MicroClaw Deployer — One-click installer
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
def _setup_windows_taskbar():
    """Set AppUserModelID and DPI awareness so the taskbar icon is crisp."""
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ai.openclaw.microclaw.installer"
        )
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class DeployerApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("MicroClaw Installer")
        self.configure(bg=BG)
        self.geometry("560x600")
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
        self._logo_image = self._load_logo()
        if self._logo_image:
            tk.Label(container, image=self._logo_image, bg=BG).pack(pady=(0, 4))
        else:
            tk.Label(container, text="🦞", font=("Segoe UI Emoji", 48),
                     bg=BG, fg=FG).pack(pady=(0, 4))

        tk.Label(container, text="MicroClaw", font=("Segoe UI", 24, "bold"),
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

        # Uninstall button (red)
        self._uninstall_btn = tk.Button(
            container, text="\u5378\u8f7d MicroClaw", command=self._on_uninstall,
            bg=ERROR, fg="#ffffff", activebackground="#cc2b22",
            activeforeground="#ffffff",
            font=("Segoe UI", 11, "bold"), bd=0,
            padx=24, pady=6, cursor="hand2", relief="flat")
        self._uninstall_btn.pack(pady=(12, 0))

        # Log output area (hidden initially)
        self._log_frame = tk.Frame(container, bg=BG)

        tk.Label(self._log_frame, text="\u8f93\u51fa\u65e5\u5fd7",
                 font=("Segoe UI", 9), bg=BG, fg=FG_DIM, anchor="w"
                 ).pack(fill="x", padx=4)

        self._log_text = tk.Text(
            self._log_frame, height=10, width=62,
            bg="#1e1e1e", fg="#cccccc", insertbackground="#cccccc",
            font=("Consolas", 9), bd=0, relief="flat",
            state="disabled", wrap="word", padx=8, pady=6)
        self._log_text.pack(fill="both", expand=True)

        # Hook logger to push lines into the text widget
        self.logger.add_listener(self._append_log_line)

    def _append_log_line(self, line: str):
        """Thread-safe append to the log text widget."""
        def _do():
            self._log_text.config(state="normal")
            self._log_text.insert("end", line + "\n")
            self._log_text.see("end")
            self._log_text.config(state="disabled")
        self.after(0, _do)

    def _show_log(self):
        """Show the log area."""
        self._log_frame.pack(pady=(12, 0), fill="both", expand=True)

    # ───────────────────── Actions ─────────────────────

    def _on_install(self):
        if self._running:
            return
        self._running = True
        self._failed = False
        self._install_btn.config(state="disabled", bg="#b0b0b0")
        self._subtitle.config(text="正在安装，请稍候…")
        self._progress_frame.pack(pady=(0, 20))
        self._show_log()
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

    def _on_uninstall(self):
        if self._running:
            return
        if not messagebox.askyesno(
            "确认卸载",
            "确定要卸载 MicroClaw 及桌面客户端吗？\n\n此操作将停止所有服务并删除相关文件。",
            icon="warning",
        ):
            return
        self._running = True
        self._install_btn.config(state="disabled", bg="#b0b0b0")
        self._uninstall_btn.config(state="disabled")
        self._subtitle.config(text="正在卸载，请稍候…")
        self._progress_frame.pack(pady=(0, 20))
        self._show_log()
        self._progress["value"] = 0
        self._progress.config(mode="indeterminate")
        self._progress.start(15)
        self._status_label.config(text="正在卸载…", fg=FG_DIM)
        threading.Thread(target=self._uninstall_thread, daemon=True).start()

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
            self._subtitle.config(text="MicroClaw 已就绪，浏览器即将打开")
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
            (55, "安装 MicroClaw…",      ws.install_openclaw_windows),
            (65, "配置系统 PATH…",      ws.add_to_path),
            (75, "写入配置文件…",       ws.write_config),
            (85, "安装桌面客户端…",     ws.install_desktop_client),
            (93, "创建桌面快捷方式…",   ws.create_desktop_shortcut),
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

    def _uninstall_thread(self):
        log = self.logger
        ws = WindowsSetup(self.config, log)
        try:
            ws.uninstall()
            self._running = False
            self._finish_uninstall_ok()
        except Exception as e:
            log.error(f"卸载异常: {e}")
            self._running = False
            self._finish_uninstall_fail(str(e))

    def _finish_uninstall_ok(self):
        def _do():
            self._progress.stop()
            self._progress.config(mode="determinate")
            self._progress["value"] = 100
            self._status_label.config(text="✓  卸载完成", fg=SUCCESS)
            self._subtitle.config(text="MicroClaw 已从您的电脑中移除")
            self._install_btn.config(state="normal", text="关闭", bg=SUCCESS,
                                      command=self.destroy)
            self._cancel_btn.pack_forget()
            self._uninstall_btn.pack_forget()
        self.after(0, _do)

    def _finish_uninstall_fail(self, msg: str):
        def _do():
            self._progress.stop()
            self._progress.config(mode="determinate")
            self._status_label.config(text=f"✗  卸载失败: {msg}", fg=ERROR)
            self._subtitle.config(text="卸载遇到问题")
            self._install_btn.config(state="normal", text="重试", bg=ACCENT,
                                      command=self._on_uninstall)
            self._uninstall_btn.config(state="normal")
        self.after(0, _do)

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
                timeout=15, env=env, creationflags=0x08000000,
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

    def _load_logo(self):
        """Load microclaw.png for the home screen logo, scaled to fit."""
        import sys
        candidates = []
        if getattr(sys, 'frozen', False):
            candidates.append(Path(sys._MEIPASS) / "microclaw.png")
            candidates.append(Path(sys.executable).parent / "microclaw.png")
        candidates.append(Path.cwd() / "microclaw.png")
        candidates.append(Path(__file__).parent / "microclaw.png")
        for png in candidates:
            if png.exists():
                try:
                    img = tk.PhotoImage(file=str(png))
                    # Scale down large images to ~128px height
                    h = img.height()
                    if h > 160:
                        factor = h // 128
                        img = img.subsample(factor, factor)
                    return img
                except Exception:
                    pass
        return None

    def _set_icon(self):
        import sys
        candidates = []
        if getattr(sys, 'frozen', False):
            candidates.append(Path(sys._MEIPASS) / "microclaw.ico")
            candidates.append(Path(sys.executable).parent / "microclaw.ico")
        candidates.append(Path.cwd() / "microclaw.ico")
        candidates.append(Path(__file__).parent / "microclaw.ico")
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
    _setup_windows_taskbar()
    app = DeployerApp()
    app.mainloop()
