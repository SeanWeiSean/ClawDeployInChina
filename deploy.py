#!/usr/bin/env python3
"""
MicroClaw Deployer — Wizard-style installer
=============================================
Multi-page wizard: Welcome → Config → Install → Complete.
Progress bar + file-level status display during installation.
"""

import os
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from deployer.config import DeployerConfig
from deployer.logger import DeployerLogger
from deployer.skill_catalog import get_certified_skills, get_certified_managed_skills
from deployer.skill_manager_ui import SkillManagerDialog
from deployer.windows_setup import WindowsSetup, DEFAULT_NODE_DIR, DEFAULT_DESKTOP_DIR

# ═══════════════════════════════════════════════════════════════
# Colour palette  (light, flat, clean)
# ═══════════════════════════════════════════════════════════════
BG           = "#ffffff"
BG_CARD      = "#f7f8fa"
BG_SIDEBAR   = "#2c3e50"
FG           = "#222222"
FG_DIM       = "#999999"
FG_SIDEBAR   = "#ecf0f1"
ACCENT       = "#4a90d9"
ACCENT_HOVER = "#3a7bc8"
SUCCESS      = "#34c759"
ERROR        = "#ff3b30"
PROGRESS_BG  = "#e8e8e8"
BTN_CANCEL   = "#e0e0e0"
BORDER       = "#e0e0e0"

WIN_WIDTH  = 680
WIN_HEIGHT = 500
SIDEBAR_W  = 180


# ═══════════════════════════════════════════════════════════════
# Windows taskbar setup
# ═══════════════════════════════════════════════════════════════
def _setup_windows_taskbar():
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


# ═══════════════════════════════════════════════════════════════
# Main Application — Wizard
# ═══════════════════════════════════════════════════════════════
class DeployerApp(tk.Tk):

    PAGES = ["欢迎", "配置", "安装", "完成"]

    def __init__(self):
        super().__init__()
        self.title("MicroClaw Installer")
        self.configure(bg=BG)
        self.geometry(f"{WIN_WIDTH}x{WIN_HEIGHT}")
        self.resizable(False, False)

        self._set_icon()

        self.config = DeployerConfig()
        self.logger = DeployerLogger()
        self._running = False
        self._failed = False
        self._selected_skills: list[str] | None = None
        self._selected_managed_skills: list[str] | None = None
        self._current_page = 0

        # Install path variables
        self._install_dir_var = tk.StringVar(value=str(DEFAULT_NODE_DIR))

        self._build_chrome()
        self._build_pages()
        self._show_page(0)

    # ─────────────────────────────────────────────────────
    # Chrome: sidebar + bottom nav
    # ─────────────────────────────────────────────────────

    def _build_chrome(self):
        # Left sidebar with step indicators
        self._sidebar = tk.Frame(self, bg=BG_SIDEBAR, width=SIDEBAR_W)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        tk.Label(self._sidebar, text="MicroClaw", font=("Segoe UI", 14, "bold"),
                 bg=BG_SIDEBAR, fg=FG_SIDEBAR).pack(pady=(28, 4))
        tk.Label(self._sidebar, text="安装向导", font=("Segoe UI", 10),
                 bg=BG_SIDEBAR, fg="#95a5a6").pack(pady=(0, 24))

        self._step_labels: list[tk.Label] = []
        for i, name in enumerate(self.PAGES):
            lbl = tk.Label(
                self._sidebar,
                text=f"  {i+1}. {name}",
                font=("Segoe UI", 10),
                bg=BG_SIDEBAR, fg="#7f8c8d",
                anchor="w", padx=16, pady=6,
            )
            lbl.pack(fill="x")
            self._step_labels.append(lbl)

        # Uninstall link at bottom of sidebar
        self._uninstall_btn = tk.Label(
            self._sidebar, text="卸载 MicroClaw",
            font=("Segoe UI", 9, "underline"),
            bg=BG_SIDEBAR, fg="#e74c3c", cursor="hand2",
        )
        self._uninstall_btn.pack(side="bottom", pady=(0, 16))
        self._uninstall_btn.bind("<Button-1>", lambda e: self._on_uninstall())

        # Right content area
        self._content = tk.Frame(self, bg=BG)
        self._content.pack(side="left", fill="both", expand=True)

        # Bottom nav bar
        self._nav = tk.Frame(self._content, bg=BG, height=56)
        self._nav.pack(side="bottom", fill="x")
        self._nav.pack_propagate(False)

        # Separator line
        tk.Frame(self._nav, bg=BORDER, height=1).pack(fill="x")

        nav_inner = tk.Frame(self._nav, bg=BG)
        nav_inner.pack(fill="x", padx=20, pady=12)

        self._btn_cancel = tk.Button(
            nav_inner, text="取消", command=self._on_cancel,
            bg=BTN_CANCEL, fg=FG, activebackground="#d0d0d0",
            font=("Segoe UI", 10), bd=0, padx=20, pady=6,
            cursor="hand2", relief="flat")
        self._btn_cancel.pack(side="left")

        self._btn_next = tk.Button(
            nav_inner, text="下一步 →", command=self._on_next,
            bg=ACCENT, fg="#ffffff", activebackground=ACCENT_HOVER,
            activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"), bd=0, padx=20, pady=6,
            cursor="hand2", relief="flat")
        self._btn_next.pack(side="right")

        self._btn_back = tk.Button(
            nav_inner, text="← 上一步", command=self._on_back,
            bg=BTN_CANCEL, fg=FG, activebackground="#d0d0d0",
            font=("Segoe UI", 10), bd=0, padx=20, pady=6,
            cursor="hand2", relief="flat")
        self._btn_back.pack(side="right", padx=(0, 8))

        # Page container
        self._page_area = tk.Frame(self._content, bg=BG)
        self._page_area.pack(fill="both", expand=True)

    # ─────────────────────────────────────────────────────
    # Page builders
    # ─────────────────────────────────────────────────────

    def _build_pages(self):
        self._pages: list[tk.Frame] = []

        # --- Page 0: Welcome ---
        p0 = tk.Frame(self._page_area, bg=BG)
        inner0 = tk.Frame(p0, bg=BG)
        inner0.place(relx=0.5, rely=0.45, anchor="center")

        self._logo_image = self._load_logo()
        if self._logo_image:
            tk.Label(inner0, image=self._logo_image, bg=BG).pack(pady=(0, 8))
        else:
            tk.Label(inner0, text="🦞", font=("Segoe UI Emoji", 48),
                     bg=BG, fg=FG).pack(pady=(0, 8))

        tk.Label(inner0, text="欢迎使用 MicroClaw 安装向导",
                 font=("Segoe UI", 16, "bold"), bg=BG, fg=FG).pack(pady=(0, 8))
        tk.Label(inner0, text="本向导将帮助您安装 MicroClaw AI 助手到您的电脑。\n"
                 "请点击「下一步」开始配置安装选项。",
                 font=("Segoe UI", 10), bg=BG, fg=FG_DIM, justify="center").pack()
        self._pages.append(p0)

        # --- Page 1: Configuration ---
        p1 = tk.Frame(self._page_area, bg=BG)

        tk.Label(p1, text="安装配置", font=("Segoe UI", 14, "bold"),
                 bg=BG, fg=FG, anchor="w").pack(fill="x", padx=24, pady=(20, 16))

        # Install location
        loc_frame = tk.LabelFrame(p1, text=" 安装位置 ", font=("Segoe UI", 10),
                                   bg=BG, fg=FG, bd=1, relief="groove", padx=12, pady=8)
        loc_frame.pack(fill="x", padx=24, pady=(0, 12))

        loc_row = tk.Frame(loc_frame, bg=BG)
        loc_row.pack(fill="x")

        self._install_dir_entry = tk.Entry(
            loc_row, textvariable=self._install_dir_var,
            font=("Consolas", 9), bg=BG_CARD, fg=FG, bd=1, relief="solid")
        self._install_dir_entry.pack(side="left", fill="x", expand=True, ipady=4)

        tk.Button(loc_row, text="浏览…", command=self._browse_install_dir,
                  bg=BG_CARD, fg=FG, font=("Segoe UI", 9), bd=1, relief="solid",
                  padx=8, cursor="hand2").pack(side="left", padx=(8, 0))

        tk.Label(loc_frame, text="OpenClaw 及 Node.js 将安装到此目录",
                 font=("Segoe UI", 8), bg=BG, fg=FG_DIM, anchor="w").pack(fill="x", pady=(4, 0))

        # Mirror selector
        mirror_frame = tk.LabelFrame(p1, text=" npm 镜像源 ", font=("Segoe UI", 10),
                                      bg=BG, fg=FG, bd=1, relief="groove", padx=12, pady=8)
        mirror_frame.pack(fill="x", padx=24, pady=(0, 12))

        self._mirror_var = tk.StringVar(value="npmmirror (淘宝)")
        ttk.Combobox(
            mirror_frame, textvariable=self._mirror_var,
            values=["npmmirror (淘宝)", "tencent (腾讯)"],
            state="readonly", width=24, font=("Segoe UI", 10)
        ).pack(anchor="w")

        # Skill manager
        skill_frame = tk.LabelFrame(p1, text=" 技能管理 ", font=("Segoe UI", 10),
                                     bg=BG, fg=FG, bd=1, relief="groove", padx=12, pady=8)
        skill_frame.pack(fill="x", padx=24, pady=(0, 12))

        skill_row = tk.Frame(skill_frame, bg=BG)
        skill_row.pack(fill="x")

        tk.Button(skill_row, text="⚙ 选择技能…", command=self._on_skill_manager,
                  bg=BG_CARD, fg=FG_DIM, activebackground="#e8e8e8",
                  font=("Segoe UI", 10), bd=1, relief="solid",
                  padx=12, pady=2, cursor="hand2").pack(side="left")

        self._skill_status = tk.Label(
            skill_row, text="使用默认认证技能", font=("Segoe UI", 9), bg=BG, fg=FG_DIM)
        self._skill_status.pack(side="left", padx=(12, 0))

        self._pages.append(p1)

        # --- Page 2: Installing ---
        p2 = tk.Frame(self._page_area, bg=BG)

        tk.Label(p2, text="正在安装", font=("Segoe UI", 14, "bold"),
                 bg=BG, fg=FG, anchor="w").pack(fill="x", padx=24, pady=(20, 8))

        self._install_step_label = tk.Label(
            p2, text="准备中…", font=("Segoe UI", 10), bg=BG, fg=FG_DIM, anchor="w")
        self._install_step_label.pack(fill="x", padx=24)

        # Progress bar
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Flat.Horizontal.TProgressbar",
                        troughcolor=PROGRESS_BG, background=ACCENT,
                        thickness=8, borderwidth=0)

        self._progress = ttk.Progressbar(
            p2, length=400, mode="determinate", maximum=100,
            style="Flat.Horizontal.TProgressbar")
        self._progress.pack(fill="x", padx=24, pady=(8, 4))

        self._progress_pct = tk.Label(
            p2, text="0%", font=("Segoe UI", 9), bg=BG, fg=FG_DIM, anchor="e")
        self._progress_pct.pack(fill="x", padx=24)

        # Log output
        log_label = tk.Label(p2, text="安装日志", font=("Segoe UI", 9),
                             bg=BG, fg=FG_DIM, anchor="w")
        log_label.pack(fill="x", padx=24, pady=(8, 2))

        self._log_text = tk.Text(
            p2, height=14, bg="#1e1e1e", fg="#cccccc",
            insertbackground="#cccccc", font=("Consolas", 9),
            bd=1, relief="solid", state="disabled", wrap="word", padx=8, pady=6)
        self._log_text.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        # Hook logger
        self.logger.add_listener(self._append_log_line)

        self._pages.append(p2)

        # --- Page 3: Complete ---
        p3 = tk.Frame(self._page_area, bg=BG)
        self._complete_inner = tk.Frame(p3, bg=BG)
        self._complete_inner.place(relx=0.5, rely=0.4, anchor="center")

        self._complete_icon = tk.Label(self._complete_inner, text="✓",
                                        font=("Segoe UI", 48), bg=BG, fg=SUCCESS)
        self._complete_icon.pack()

        self._complete_title = tk.Label(self._complete_inner, text="安装完成！",
                                         font=("Segoe UI", 16, "bold"), bg=BG, fg=FG)
        self._complete_title.pack(pady=(8, 4))

        self._complete_msg = tk.Label(
            self._complete_inner, text="MicroClaw 已成功安装到您的电脑。",
            font=("Segoe UI", 10), bg=BG, fg=FG_DIM, justify="center")
        self._complete_msg.pack()

        self._pages.append(p3)

    # ─────────────────────────────────────────────────────
    # Page navigation
    # ─────────────────────────────────────────────────────

    def _show_page(self, idx: int):
        # Hide all pages
        for p in self._pages:
            p.place_forget()

        self._current_page = idx
        self._pages[idx].place(x=0, y=0, relwidth=1, relheight=1)

        # Update sidebar highlights
        for i, lbl in enumerate(self._step_labels):
            if i == idx:
                lbl.config(fg=FG_SIDEBAR, font=("Segoe UI", 10, "bold"))
            elif i < idx:
                lbl.config(fg="#27ae60", font=("Segoe UI", 10))
            else:
                lbl.config(fg="#7f8c8d", font=("Segoe UI", 10))

        # Update nav buttons
        if idx == 0:
            self._btn_back.pack_forget()
            self._btn_next.config(text="下一步 →", command=self._on_next, bg=ACCENT, state="normal")
            self._btn_cancel.config(text="取消", command=self._on_cancel, state="normal")
            self._btn_cancel.pack(side="left")
        elif idx == 1:
            self._btn_back.pack(side="right", padx=(0, 8))
            self._btn_next.config(text="开始安装 ▶", command=self._on_start_install,
                                  bg=ACCENT, state="normal")
            self._btn_cancel.config(text="取消", command=self._on_cancel, state="normal")
            self._btn_cancel.pack(side="left")
        elif idx == 2:
            self._btn_back.pack_forget()
            self._btn_next.config(text="安装中…", state="disabled", bg="#b0b0b0")
            self._btn_cancel.config(text="取消安装", command=self._on_cancel_install, state="normal")
            self._btn_cancel.pack(side="left")
        elif idx == 3:
            self._btn_back.pack_forget()
            self._btn_cancel.pack_forget()
            self._btn_next.config(text="完成", command=self.destroy, bg=SUCCESS, state="normal")
            self._uninstall_btn.pack_forget()

    def _on_next(self):
        if self._current_page < len(self.PAGES) - 1:
            self._show_page(self._current_page + 1)

    def _on_back(self):
        if self._current_page > 0:
            self._show_page(self._current_page - 1)

    def _on_cancel(self):
        self.destroy()

    def _on_cancel_install(self):
        if self._running:
            self._running = False

    # ─────────────────────────────────────────────────────
    # Config page actions
    # ─────────────────────────────────────────────────────

    def _browse_install_dir(self):
        d = filedialog.askdirectory(title="选择安装目录", initialdir=self._install_dir_var.get())
        if d:
            self._install_dir_var.set(d)

    def _on_skill_manager(self):
        preselected = self._selected_skills if self._selected_skills is not None else get_certified_skills()
        preselected_managed = (self._selected_managed_skills
                               if self._selected_managed_skills is not None
                               else get_certified_managed_skills())
        dialog = SkillManagerDialog(self, preselected=preselected,
                                    preselected_managed=preselected_managed)
        self.wait_window(dialog)
        if dialog.result is not None:
            self._selected_skills = dialog.result
            self._selected_managed_skills = dialog.managed_result
            nb = len(dialog.result)
            nm = len(dialog.managed_result) if dialog.managed_result else 0
            self._skill_status.config(text=f"已选择 {nb} 内置 + {nm} 托管技能")

    # ─────────────────────────────────────────────────────
    # Install
    # ─────────────────────────────────────────────────────

    def _on_start_install(self):
        if self._running:
            return
        self._running = True
        self._failed = False

        # Apply config from UI
        mirror_sel = self._mirror_var.get()
        if "tencent" in mirror_sel.lower():
            self.config.set("npm.registry", "http://mirrors.cloud.tencent.com/npm/")
        else:
            self.config.set("npm.registry", "https://registry.npmmirror.com")

        skills = self._selected_skills if self._selected_skills is not None else get_certified_skills()
        managed_skills = (self._selected_managed_skills
                          if self._selected_managed_skills is not None
                          else get_certified_managed_skills())
        self.config.set("skills.enable", True)
        self.config.set("skills.allowBundled", skills)
        self.config.set("skills.allowManaged", managed_skills)

        # Apply custom install directory
        install_dir = self._install_dir_var.get().strip()
        if install_dir:
            os.environ["OPENCLAW_NODE_DIR"] = install_dir

        # Switch to install page
        self._show_page(2)

        threading.Thread(target=self._install_thread, daemon=True).start()

    def _set_progress(self, pct: int, text: str):
        def _do():
            self._progress["value"] = pct
            self._progress_pct.config(text=f"{pct}%")
            self._install_step_label.config(text=text, fg=FG_DIM)
        self.after(0, _do)

    def _append_log_line(self, line: str):
        def _do():
            self._log_text.config(state="normal")
            self._log_text.insert("end", line + "\n")
            self._log_text.see("end")
            self._log_text.config(state="disabled")
        self.after(0, _do)

    def _install_thread(self):
        log = self.logger

        # Re-read install dir (may have been changed)
        install_dir = self._install_dir_var.get().strip()
        if install_dir:
            os.environ["OPENCLAW_NODE_DIR"] = install_dir

        ws = WindowsSetup(self.config, log)

        steps = [
            (5,  "正在检查 Git…",             ws.ensure_git),
            (12, "正在检查 Node.js…",          ws.check_node_windows),
            (28, "正在安装 Node.js…",          ws.install_node_windows),
            (38, "正在配置 npm 镜像…",         ws.setup_npm_mirror),
            (55, "正在安装 MicroClaw 核心…",    ws.install_openclaw_windows),
            (65, "正在配置系统 PATH…",         ws.add_to_path),
            (75, "正在写入配置文件…",          ws.write_config),
            (85, "正在安装桌面客户端…",        ws.install_desktop_client),
            (92, "正在创建桌面快捷方式…",      ws.create_desktop_shortcut),
            (97, "正在验证安装…",              self._verify),
        ]

        # Pre-flight
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
                if fn == ws.check_node_windows:
                    node_ok = bool(result)
                    continue

                if not result and fn not in (ws.check_node_windows, ws.run_onboard):
                    self._finish_fail(label.replace("正在", "").replace("…", "") + " 失败")
                    self._running = False
                    return
            except Exception as e:
                log.error(f"{label} exception: {e}")
                if fn not in (ws.check_node_windows, ws.run_onboard):
                    self._finish_fail(label.replace("正在", "").replace("…", "") + " 失败")
                    self._running = False
                    return

        self._running = False
        self._finish_ok()

    def _finish_ok(self):
        def _do():
            self._set_progress(100, "安装完成！")
            self._complete_icon.config(text="✓", fg=SUCCESS)
            self._complete_title.config(text="安装完成！", fg=FG)
            self._complete_msg.config(text="MicroClaw 已成功安装到您的电脑。\n浏览器即将打开控制台。")
            self._show_page(3)
        self.after(0, _do)

    def _finish_fail(self, msg: str):
        def _do():
            self._failed = True
            self._complete_icon.config(text="✗", fg=ERROR)
            self._complete_title.config(text="安装失败", fg=ERROR)
            self._complete_msg.config(text=f"{msg}\n请检查网络连接后重试。")
            self._show_page(3)
            self._btn_next.config(text="重试", command=self._on_retry, bg=ACCENT, state="normal")
            self._btn_cancel.pack(side="left")
            self._btn_cancel.config(text="关闭", command=self.destroy)
        self.after(0, _do)

    def _on_retry(self):
        self._show_page(1)

    # ─────────────────────────────────────────────────────
    # Uninstall
    # ─────────────────────────────────────────────────────

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
        self._show_page(2)
        self._install_step_label.config(text="正在卸载…")
        self._progress.config(mode="indeterminate")
        self._progress.start(15)
        self._progress_pct.config(text="")
        self._btn_cancel.config(state="disabled")
        threading.Thread(target=self._uninstall_thread, daemon=True).start()

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
            self._complete_icon.config(text="✓", fg=SUCCESS)
            self._complete_title.config(text="卸载完成", fg=FG)
            self._complete_msg.config(text="MicroClaw 已从您的电脑中移除。")
            self._show_page(3)
        self.after(0, _do)

    def _finish_uninstall_fail(self, msg: str):
        def _do():
            self._progress.stop()
            self._progress.config(mode="determinate")
            self._complete_icon.config(text="✗", fg=ERROR)
            self._complete_title.config(text="卸载失败", fg=ERROR)
            self._complete_msg.config(text=f"{msg}")
            self._show_page(3)
            self._btn_next.config(text="重试", command=self._on_uninstall, bg=ACCENT, state="normal")
            self._btn_cancel.pack(side="left")
            self._btn_cancel.config(text="关闭", command=self.destroy)
        self.after(0, _do)

    # ─────────────────────────────────────────────────────
    # Verify
    # ─────────────────────────────────────────────────────

    def _verify(self) -> bool:
        cmd = self._find_openclaw_cmd()
        if not cmd:
            return False
        install_dir = Path(self._install_dir_var.get().strip()) if self._install_dir_var.get().strip() else DEFAULT_NODE_DIR
        env = os.environ.copy()
        env["PATH"] = str(install_dir) + os.pathsep + env.get("PATH", "")
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

    def _find_openclaw_cmd(self) -> list[str] | None:
        install_dir = Path(self._install_dir_var.get().strip()) if self._install_dir_var.get().strip() else DEFAULT_NODE_DIR
        for name in ("openclaw.cmd", "openclaw"):
            p = install_dir / name
            if p.exists():
                return [str(p)]
        found = shutil.which("openclaw")
        if found:
            return [found]
        npm_prefix = Path.home() / "AppData" / "Roaming" / "npm"
        for name in ("openclaw.cmd", "openclaw"):
            p = npm_prefix / name
            if p.exists():
                return [str(p)]
        return None

    # ─────────────────────────────────────────────────────
    # Resource loading
    # ─────────────────────────────────────────────────────

    def _load_logo(self):
        import sys
        candidates = []
        if getattr(sys, 'frozen', False):
            candidates.append(Path(sys._MEIPASS) / "microclaw.png")
            candidates.append(Path(sys.executable).parent / "microclaw.png")
        candidates.append(Path(__file__).parent / "microclaw.png")
        for png in candidates:
            if png.exists():
                try:
                    img = tk.PhotoImage(file=str(png))
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
