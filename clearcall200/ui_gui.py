"""桌面客户端（对齐 remote-mic-app 的界面语言）：浅色、左侧栏、按键卡片式映射。

布局：
  左栏（连接 / 按键 / 统计 / 权限 / 关于）
  主区：标题「按键映射」+ 启用开关 + 右上设备卡 + 中间耳机图 + 左右按键卡片（单击/双击/长按）
  底栏：状态点 + 学习模式开关 + 保存 / 恢复默认

职责不变：主窗口负责配置，常驻挂件负责保活与点亮反馈（同一 Tk root，挂件是 Toplevel）。
规范：openspec/specs/desktop-widget/spec.md
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox, simpledialog

from .rules import TRIGGERS
from .widget import build_widget

# ---- 视觉 token（对齐参考项目的浅色 macOS 风格）----
BG = "#F5F5F7"
SIDEBAR = "#FBFBFD"
CARD = "#FFFFFF"
BORDER = "#E5E5EA"
TEXT = "#1D1D1F"
SUB = "#86868B"
ACCENT = "#0A84FF"
ACCENT_BG = "#EAF3FF"
GREEN = "#34C759"
GRAY = "#C7C7CC"
CELL = "#F2F2F7"
CELL_HOVER = "#E8E8ED"

FONT = "Helvetica Neue"

# ---- 物理键 → 可用手势（顺序即界面展示顺序）----
KEY_LAYOUT = [
    ("mute", "🎧", "静音键", [("单击", "mute:click")]),
    ("call", "📞", "通话键", [("单击", "call:click"), ("双击", "call:double"), ("长按", "call:long")]),
    ("volp", "＋", "音量 +", [("单击", "volp:click"), ("长按", "volp:long")]),
    ("volm", "－", "音量 −", [("单击", "volm:click")]),
]
LEFT_KEYS = ("mute", "call")
RIGHT_KEYS = ("volp", "volm")

ACTION_LABEL = {
    "none": "未设置",
    "ptt_toggle": "按下说话",
    "ptt_hold": "按住说话",
    "obs_toggle_mute": "OBS 静音切换",
}


def describe_action(action: str) -> str:
    a = (action or "none").strip()
    if a in ACTION_LABEL:
        return ACTION_LABEL[a]
    if a.startswith("hid_send"):
        parts = a.split(None, 1)
        return parts[1] if len(parts) > 1 else "发送按键"
    if a.startswith("notify"):
        return a[len("notify"):].strip().strip('"“”') or "通知"
    return a


class Switch(tk.Canvas):
    """macOS 风格开关（自绘，避免 tk.Checkbutton 在 mac 上的怪异样式）。"""

    def __init__(self, master, value: bool = True, command=None):
        super().__init__(master, width=44, height=24, bg=master["bg"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self._value = value
        self._command = command
        self.bind("<Button-1>", self._toggle)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        color = ACCENT if self._value else GRAY
        self.create_oval(2, 3, 21, 22, fill=color, outline=color)
        self.create_oval(23, 3, 42, 22, fill=color, outline=color)
        self.create_rectangle(11, 3, 33, 22, fill=color, outline=color)
        x = 32 if self._value else 12
        self.create_oval(x - 9, 3, x + 9, 21, fill="#FFFFFF", outline="#FFFFFF")

    def _toggle(self, _e=None) -> None:
        self._value = not self._value
        self._draw()
        if self._command:
            self._command(self._value)

    def set(self, value: bool) -> None:
        self._value = bool(value)
        self._draw()

    def get(self) -> bool:
        return self._value


class KeyCell(tk.Frame):
    """一个「手势 → 动作」格子，点击弹出动作选择。"""

    def __init__(self, master, gesture: str, trigger: str, client: "DesktopClient"):
        super().__init__(master, bg=CELL, bd=0)
        self.trigger = trigger
        self.client = client
        self.gesture = tk.Label(self, text=gesture, bg=CELL, fg=SUB, font=(FONT, 11))
        self.gesture.pack(pady=(8, 1))
        self.action = tk.Label(self, text="未设置", bg=CELL, fg=TEXT, font=(FONT, 12), wraplength=120)
        self.action.pack(pady=(0, 8))
        for w in (self, self.gesture, self.action):
            w.bind("<Button-1>", self._open_menu)
            w.bind("<Enter>", lambda e: self._paint(CELL_HOVER))
            w.bind("<Leave>", lambda e: self._paint(CELL))
        self.refresh()

    def _paint(self, color: str) -> None:
        for w in (self, self.gesture, self.action):
            w.configure(bg=color)

    def refresh(self) -> None:
        action = self.client.app.rules.action_for_trigger(self.trigger)
        self.action.configure(text=describe_action(action),
                              fg=TEXT if action != "none" else SUB)

    def _open_menu(self, _e=None) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="未设置", command=lambda: self.client.set_action(self.trigger, "none"))
        menu.add_separator()
        menu.add_command(label="按下说话（切换）", command=lambda: self.client.set_action(self.trigger, "ptt_toggle"))
        menu.add_command(label="按住说话", command=lambda: self.client.set_action(self.trigger, "ptt_hold"))
        menu.add_command(label="OBS 静音切换", command=lambda: self.client.set_action(self.trigger, "obs_toggle_mute"))
        menu.add_separator()
        menu.add_command(label="发送按键…", command=self._pick_hid)
        menu.add_command(label="发送通知…", command=self._pick_notify)
        menu.add_separator()
        menu.add_command(label="按一下试试", command=lambda: self.client.app._handle_trigger(self.trigger, "gui 测试"))
        try:
            menu.tk_popup(self.winfo_rootx() + 20, self.winfo_rooty() + 20)
        finally:
            menu.grab_release()

    def _pick_hid(self) -> None:
        key = simpledialog.askstring("发送按键", "按键名（如 F13 / SPACE）", parent=self, initialvalue="F13")
        if key:
            self.client.set_action(self.trigger, f"hid_send {key.strip().upper()}")

    def _pick_notify(self) -> None:
        text = simpledialog.askstring("发送通知", "通知内容", parent=self, initialvalue="已触发")
        if text:
            self.client.set_action(self.trigger, f'notify"{text}"')


class DesktopClient:
    W, H = 1180, 840

    def __init__(self, app, widget_mode: str = "bar", demo: bool = False):
        self.app = app
        self.queue: queue.Queue[str] = queue.Queue()
        self.cells: list[KeyCell] = []

        root = tk.Tk()
        self.root = root
        root.title("ClearCall200 · 按键映射")
        root.configure(bg=BG)
        self._center()
        root.minsize(1000, 720)

        self._build_sidebar()
        self._build_bottom()
        self._build_main()
        self._show_page("按键")

        self.widget = build_widget(app, widget_mode, master=root)
        self.widget.on_closed = self._quit_all
        self.widget.on_settings = self.show

        app.edge_listener = self._on_edge
        app.trigger_listener = self._on_trigger
        app.ui.capture = self.queue.put
        app.ui.interactive = False

        root.protocol("WM_DELETE_WINDOW", self.hide)
        root.after(80, self._tick)
        root.after(20, self._pump_volume_loop)
        if demo:
            self._start_demo()

    # ---------------- 布局 ----------------
    def _center(self) -> None:
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = max(0, (sw - self.W) // 2), max(0, (sh - self.H) // 3)
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

    def _build_sidebar(self) -> None:
        bar = tk.Frame(self.root, bg=SIDEBAR, width=132)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)
        self._nav_items = {}
        for icon, name in (("🔗", "连接"), ("⌨", "按键"), ("▦", "统计"), ("🛡", "权限"), ("ⓘ", "关于")):
            item = tk.Frame(bar, bg=SIDEBAR, cursor="hand2")
            item.pack(fill="x", pady=6, padx=8)
            glyph = tk.Label(item, text=icon, bg=SIDEBAR, fg=SUB, font=(FONT, 20))
            glyph.pack(pady=(8, 0))
            label = tk.Label(item, text=name, bg=SIDEBAR, fg=SUB, font=(FONT, 12))
            label.pack(pady=(2, 8))
            for w in (item, glyph, label):
                w.bind("<Button-1>", lambda e, n=name: self._show_page(n))
            self._nav_items[name] = (item, glyph, label)

    def _build_main(self) -> None:
        self.main = tk.Frame(self.root, bg=BG)
        self.main.pack(side="top", fill="both", expand=True, padx=(20, 24), pady=(18, 0))
        self.pages: dict[str, tk.Frame] = {}
        for name in ("连接", "按键", "统计", "权限", "关于"):
            self.pages[name] = tk.Frame(self.main, bg=BG)

        self._build_map_page(self.pages["按键"])
        self._build_devices_page(self.pages["连接"])
        self._build_stats_page(self.pages["统计"])
        self._build_perms_page(self.pages["权限"])
        self._build_about_page(self.pages["关于"])

    def _build_bottom(self) -> None:
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(side="bottom", fill="x", padx=(20, 24), pady=(6, 16))
        card = tk.Frame(wrap, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=12)

        self.dot = tk.Label(inner, text="●", bg=CARD, fg=GRAY, font=(FONT, 13))
        self.dot.pack(side="left")
        self.bottom_status = tk.Label(inner, text="按键功能未连接", bg=CARD, fg=TEXT, font=(FONT, 12))
        self.bottom_status.pack(side="left", padx=(6, 24))

        tk.Label(inner, text="学习模式", bg=CARD, fg=TEXT, font=(FONT, 12)).pack(side="left")
        self.learn_switch = Switch(inner, value=False, command=self._on_learn_toggle)
        self.learn_switch.pack(side="left", padx=(8, 4))
        tk.Label(inner, text="只检测、不执行动作", bg=CARD, fg=SUB, font=(FONT, 11)).pack(side="left")

        reset = tk.Label(inner, text="恢复默认", bg=CELL, fg=TEXT, font=(FONT, 12),
                         padx=14, pady=6, cursor="hand2")
        reset.pack(side="right")
        reset.bind("<Button-1>", lambda e: self._restore_defaults())

        save = tk.Label(inner, text="保存", bg=ACCENT, fg="#FFFFFF", font=(FONT, 12),
                        padx=16, pady=6, cursor="hand2")
        save.pack(side="right", padx=(0, 8))
        save.bind("<Button-1>", lambda e: self.app._execute("save"))

    # ---------------- 页面：按键 ----------------
    def _build_map_page(self, page: tk.Frame) -> None:
        head = tk.Frame(page, bg=BG)
        head.pack(fill="x", pady=(0, 14))
        tk.Label(head, text="按键映射", bg=BG, fg=TEXT, font=(FONT, 24, "bold")).pack(side="left")

        self.enable_switch = Switch(head, value=True, command=self._on_enable_toggle)
        tk.Label(head, text="启用自定义按键功能", bg=BG, fg=TEXT, font=(FONT, 12)).pack(side="right", padx=(0, 10))
        self.enable_switch.pack(side="right", padx=10)

        self.device_box = tk.Frame(head, bg=BG)
        self.device_box.pack(side="right", padx=(0, 18))
        self._build_device_cards()

        body = tk.Frame(page, bg=BG)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y")
        center = tk.Frame(body, bg=BG)
        center.pack(side="left", fill="both", expand=True, padx=18)
        right = tk.Frame(body, bg=BG)
        right.pack(side="right", fill="y")

        self._build_center_image(center)
        for key, icon, title, gestures in KEY_LAYOUT:
            target = left if key in LEFT_KEYS else right
            self._build_key_card(target, icon, title, gestures)

    def _build_center_image(self, parent: tk.Frame) -> None:
        holder = tk.Frame(parent, bg=BG)
        holder.pack(fill="both", expand=True)
        try:
            self._photo = tk.PhotoImage(file=asset_path("assets/headset-ui.png"))
            tk.Label(holder, image=self._photo, bg=BG, bd=0).pack(expand=True)
        except Exception:
            tk.Label(holder, text="🎧", bg=BG, fg=SUB, font=(FONT, 72)).pack(expand=True)
        tk.Label(holder, text="按键时对应卡片会高亮", bg=BG, fg=SUB, font=(FONT, 11)).pack(pady=(0, 8))

    def _build_key_card(self, parent: tk.Frame, icon: str, title: str, gestures) -> None:
        card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 12))
        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(row, text=f"{icon}  {title}", bg=CARD, fg=TEXT, font=(FONT, 13, "bold")).pack(side="left")

        grid = tk.Frame(card, bg=CARD)
        grid.pack(fill="x", padx=10, pady=(0, 10))
        for col, (gesture, trigger) in enumerate(gestures):
            cell = KeyCell(grid, gesture, trigger, self)
            cell.grid(row=0, column=col, padx=4, pady=4, sticky="nsew")
            grid.grid_columnconfigure(col, weight=1)
            self.cells.append(cell)

    def _build_device_cards(self) -> None:
        devices = bluetooth_devices()
        shown = devices[:2]
        for dev in shown:
            self._device_card(self.device_box, dev, highlight=dev.get("name", "").startswith("EDIFIER"))
        if len(shown) < 2:
            card = tk.Frame(self.device_box, bg="#F0F0F3", highlightbackground=BORDER, highlightthickness=1)
            card.pack(side="left", padx=4)
            tk.Label(card, text="＋ 其他设备", bg="#F0F0F3", fg=SUB, font=(FONT, 12)).pack(padx=18, pady=16)

    def _device_card(self, parent, dev: dict, highlight: bool = False) -> None:
        bg = ACCENT_BG if highlight else CARD
        card = tk.Frame(parent, bg=bg, highlightbackground=ACCENT if highlight else BORDER,
                        highlightthickness=1)
        card.pack(side="left", padx=4)
        top = tk.Frame(card, bg=bg)
        top.pack(fill="x", padx=12, pady=(8, 2))
        tk.Label(top, text=dev.get("name", "未知设备"), bg=bg, fg=ACCENT if highlight else TEXT,
                 font=(FONT, 13, "bold")).pack(side="left")
        tk.Label(top, text="✓" if dev.get("connected") else "", bg=bg, fg=ACCENT,
                 font=(FONT, 12)).pack(side="right")
        info = tk.Frame(card, bg=bg)
        info.pack(fill="x", padx=12, pady=(0, 8))
        ok = dev.get("connected")
        tk.Label(info, text="●", bg=bg, fg=GREEN if ok else GRAY, font=(FONT, 11)).pack(side="left")
        tk.Label(info, text="已连接" if ok else "未连接", bg=bg, fg=SUB, font=(FONT, 11)).pack(side="left", padx=4)
        if dev.get("battery"):
            tk.Label(info, text=f"🔋 {dev['battery']}", bg=bg, fg=SUB, font=(FONT, 11)).pack(side="left", padx=8)

    # ---------------- 其他页面 ----------------
    def _page_title(self, page: tk.Frame, text: str, desc: str) -> tk.Frame:
        tk.Label(page, text=text, bg=BG, fg=TEXT, font=(FONT, 26, "bold")).pack(anchor="w")
        tk.Label(page, text=desc, bg=BG, fg=SUB, font=(FONT, 12)).pack(anchor="w", pady=(2, 16))
        body = tk.Frame(page, bg=BG)
        body.pack(fill="both", expand=True)
        return body

    def _build_devices_page(self, page: tk.Frame) -> None:
        body = self._page_title(page, "连接", "蓝牙设备与本机采集通道")
        devices = bluetooth_devices()
        if not devices:
            tk.Label(body, text="未读取到蓝牙设备", bg=BG, fg=SUB, font=(FONT, 12)).pack(anchor="w")
        for dev in devices:
            card = tk.Frame(body, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            card.pack(fill="x", pady=4)
            row = tk.Frame(card, bg=CARD)
            row.pack(fill="x", padx=14, pady=10)
            tk.Label(row, text="●", bg=CARD, fg=GREEN if dev["connected"] else GRAY,
                     font=(FONT, 12)).pack(side="left")
            tk.Label(row, text=dev["name"], bg=CARD, fg=TEXT, font=(FONT, 13, "bold")).pack(side="left", padx=6)
            meta = dev["address"]
            if dev.get("battery"):
                meta += f"   🔋 {dev['battery']}"
            tk.Label(row, text=meta, bg=CARD, fg=SUB, font=(FONT, 11)).pack(side="right")

        self.capture_label = tk.Label(body, text="", bg=BG, fg=SUB, font=(FONT, 12), justify="left")
        self.capture_label.pack(anchor="w", pady=(14, 0))

    def _build_stats_page(self, page: tk.Frame) -> None:
        body = self._page_title(page, "统计", "本次运行期间各触发源的识别次数")
        self.stat_rows = {}
        for trigger in TRIGGERS:
            card = tk.Frame(body, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            card.pack(fill="x", pady=3)
            row = tk.Frame(card, bg=CARD)
            row.pack(fill="x", padx=14, pady=8)
            tk.Label(row, text=trigger, bg=CARD, fg=TEXT, font=(FONT, 12)).pack(side="left")
            num = tk.Label(row, text="0", bg=CARD, fg=ACCENT, font=(FONT, 15, "bold"))
            num.pack(side="right")
            self.stat_rows[trigger] = num

    def _build_perms_page(self, page: tk.Frame) -> None:
        body = self._page_title(page, "权限", "macOS 需要授权才能监听耳机按键")
        card = tk.Frame(body, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=4)
        tk.Label(card, text="辅助功能 / 输入监控", bg=CARD, fg=TEXT,
                 font=(FONT, 13, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        tk.Label(card, text="耳机按键被系统投影成媒体键事件，监听/拦截它需要这两项权限。\n"
                            "已启用拦截：按下耳机按键不会再改系统音量、不会再触发播放暂停。\n"
                            "勾选运行本程序的终端后重启客户端即可。",
                 bg=CARD, fg=SUB, font=(FONT, 12), justify="left").pack(anchor="w", padx=14, pady=(0, 10))

        self.perm_input = tk.Label(body, text="", bg=BG, fg=TEXT, font=(FONT, 12), justify="left")
        self.perm_input.pack(anchor="w", pady=(12, 2))
        self.perm_ctrl = tk.Label(body, text="", bg=BG, fg=TEXT, font=(FONT, 12), justify="left")
        self.perm_ctrl.pack(anchor="w", pady=(0, 2))
        self.perm_label = tk.Label(body, text="", bg=BG, fg=SUB, font=(FONT, 12), justify="left")
        self.perm_label.pack(anchor="w", pady=(6, 8))

        row = tk.Frame(body, bg=BG)
        row.pack(anchor="w", pady=(0, 6))

        req = tk.Label(row, text="申请权限（弹出系统授权框）", bg=ACCENT_BG, fg=ACCENT,
                       font=(FONT, 12), padx=16, pady=7, cursor="hand2")
        req.pack(side="left")
        req.bind("<Button-1>", lambda e: request_permissions())

        recheck = tk.Label(row, text="重新检测", bg=ACCENT, fg="#FFFFFF",
                           font=(FONT, 12), padx=16, pady=7, cursor="hand2")
        recheck.pack(side="left", padx=(10, 0))
        recheck.bind("<Button-1>", lambda e: self._recheck_perms())

        self.perm_result = tk.Label(body, text="", bg=BG, fg=SUB, font=(FONT, 12), justify="left")
        self.perm_result.pack(anchor="w", pady=(2, 6))

        nav = tk.Frame(body, bg=BG)
        nav.pack(anchor="w", pady=(10, 4))

        for text, pane in (("打开「输入监控」设置", "Privacy_ListenEvent"),
                           ("打开「辅助功能」设置", "Privacy_Accessibility")):
            b = tk.Label(nav, text=text, bg=CELL, fg=TEXT, font=(FONT, 12),
                         padx=14, pady=7, cursor="hand2")
            b.pack(side="left", padx=(0, 8))
            b.bind("<Button-1>", lambda e, p=pane: subprocess.run(
                ["open", f"x-apple.systempreferences:com.apple.preference.security?{p}"], check=False))

        tk.Label(body, text="应用身份（授权按这个名字找）：ClearCall200 · com.zhaojian.clearcall200\n"
                            "路径：~/Applications/ClearCall200.app",
                 bg=BG, fg=SUB, font=(FONT, 11), justify="left").pack(anchor="w", pady=(6, 2))

    def _build_about_page(self, page: tk.Frame) -> None:
        body = self._page_title(page, "关于", "ClearCall 200 按键自定义客户端")
        for line in (
            "单体单进程 · 仅标准库 + pyobjc（macOS 媒体键采集）",
            "规范：openspec/specs/*（改行为先改 spec）",
            "触发源：mute:click / call:click / call:long / call:double / volp:click / volp:long / volm:click",
            "动作：none / ptt_toggle / ptt_hold / hid_send / obs_toggle_mute / notify",
        ):
            tk.Label(body, text=line, bg=BG, fg=SUB, font=(FONT, 12), justify="left").pack(anchor="w", pady=3)

    # ---------------- 状态与交互 ----------------
    def _show_page(self, name: str) -> None:
        for page in self.pages.values():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        for key, (item, glyph, label) in self._nav_items.items():
            on = key == name
            bg = ACCENT_BG if on else SIDEBAR
            fg = ACCENT if on else SUB
            item.configure(bg=bg)
            glyph.configure(bg=bg, fg=fg)
            label.configure(bg=bg, fg=fg)

    def set_action(self, trigger: str, action: str) -> None:
        idx = TRIGGERS.index(trigger)
        self.app._execute(f"set {idx} {action}")
        self.refresh()

    def refresh(self) -> None:
        for cell in self.cells:
            cell.refresh()

    def _recheck_perms(self) -> None:
        """重新检测：真实重建一次事件监听，结果直接显示在页面上。"""
        request_permissions()          # 缺权限时弹出系统请求框 / 把本应用登记进两个列表
        self.app.stop_media_keys()
        ok = self.app.attach_media_keys()
        listen_ok, ctrl_ok = permission_state()
        if ok:
            msg = ("✅ 检测通过：已能监听并拦截耳机按键。\n"
                   "若音量仍会变，说明系统缓存未刷新 —— 完全退出应用（⌘Q）后重新打开一次。")
        elif listen_ok and not ctrl_ok:
            msg = ("⚠️ 输入监控已授权，但「辅助功能」未授权：能听到按键，但吞不掉事件。\n"
                   "请到 隐私与安全性 → 辅助功能 勾选 ClearCall200，然后点本按钮再检测。")
        else:
            granted = self.app.perm_granted_before
            if granted:
                msg = ("❌ 系统里已有授权记录，但当前进程没有生效 —— 这是 macOS 的规则：\n"
                       "授权只对「之后启动」的进程有效。请 ⌘Q 完全退出，再双击打开应用。\n"
                       "（重新打开后不要再点检测，直接看这两行状态是否变绿）")
            else:
                msg = ("❌ 系统里还没有本应用的授权记录。请在下面两个按钮打开的页面里，\n"
                       "把 ClearCall200 打开开关；然后 ⌘Q 退出、重新打开应用。\n"
                       "若列表里有多条 ClearCall200，删掉失效的旧条目，只留当前这一个。")
        self.perm_result.configure(text=msg)
        self._refresh_status()

    def _on_enable_toggle(self, value: bool) -> None:
        if value:
            self.app._cmd_normal("gui switch")
        else:
            self.app._cmd_learn()

    def _on_learn_toggle(self, value: bool) -> None:
        if value:
            self.app._cmd_learn()
        else:
            self.app._cmd_normal("gui switch")

    def _restore_defaults(self) -> None:
        if not messagebox.askyesno("恢复默认", "把所有按键映射改回默认？", parent=self.root):
            return
        from .config import default_config
        from .rules import RuleSet
        fresh = RuleSet(default_config())
        for i, row in enumerate(fresh.rules):
            self.app._execute(f"set {i} {row['action']}")
        self.refresh()

    def _start_demo(self, i: int = 0) -> None:
        demo = [("call", "call:click"), ("volp", "volp:click"), ("mute", "mute:click"),
                ("call", "call:click"), ("volm", "volm:click")]
        key, trigger = demo[i % len(demo)]
        # 走真实链路：队列 → pump_edges → parser → edge/trigger 回调
        self.app._edge_q.put(("press", key))
        self.root.after(400, lambda: self.app._edge_q.put(("release", key)))
        self.root.after(900, lambda: self.app._handle_trigger(trigger, "gui 测试"))
        self.root.after(1800, lambda: self._start_demo(i + 1))

    # ---------------- 窗口显隐 ----------------
    def hide(self) -> None:
        self.root.withdraw()
        self.app.ui.append("OK 主窗口已隐藏（挂件常驻，点挂件上的 ⚙ 恢复）")

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def _quit_all(self) -> None:
        self.app.quit = True
        try:
            self.app._cleanup()
        finally:
            try:
                self.root.destroy()
            except tk.TclError:
                pass

    # ---------------- 按键反馈（真实采集走这条链路） ----------------
    def _on_edge(self, kind: str, key: str) -> None:
        """按下/松开：挂件胶囊 + 主窗口对应卡片同时高亮。"""
        self.widget.on_edge(kind, key)
        for cell in self.cells:
            if cell.trigger.split(":")[0] != key:
                continue
            if kind == "press":
                cell._paint(ACCENT_BG)
                cell.action.configure(fg=ACCENT)
            else:
                self.root.after(600, lambda c=cell: (c._paint(CELL), c.refresh()))

    def _on_trigger(self, trigger: str) -> None:
        self.widget.on_trigger(trigger)
        for cell in self.cells:
            if cell.trigger != trigger:
                continue
            cell._paint(ACCENT_BG)
            cell.action.configure(fg=ACCENT)
            self.root.after(600, lambda c=cell: (c._paint(CELL), c.refresh()))

    def _pump_volume_loop(self) -> None:
        """音量键事件单独高频抽取（20ms），不受 80ms 界面心跳影响。"""
        try:
            self.app.pump_volume()
        except Exception:
            pass
        self.root.after(20, self._pump_volume_loop)

    # ---------------- 轮询 ----------------
    def _tick(self) -> None:
        if self.app.quit:
            return
        if getattr(self.app.rt, "stop_requested", False):
            self._quit_all()
            return
        self.app.pump_edges()
        self.app.pump_volume()
        self.app._dispatch_parser_events(self.app.parser.tick(time.monotonic()))
        self.app._housekeeping()

        drained = 0
        while drained < 30:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
            drained += 1

        self._refresh_status()
        self.root.after(80, self._tick)

    def _refresh_status(self) -> None:
        st = self.app.state
        capture = getattr(self.app, "media_keys_ok", False)
        self.dot.configure(fg=GREEN if capture else GRAY)
        mode = "拦截中" if getattr(self.app, "intercept_on", False) else ""
        text = f"按键功能{'已连接' if capture else '未连接（缺辅助功能权限）'}"
        text += f"（{mode}）" if mode else ""
        text += f"  ·  {st.call_label()}"
        if st.is_learn():
            text += "  ·  学习中（只检测）"
        self.bottom_status.configure(text=text)

        if self.learn_switch.get() != st.is_learn():
            self.learn_switch.set(st.is_learn())
        if self.enable_switch.get() == st.is_learn():
            self.enable_switch.set(not st.is_learn())

        if hasattr(self, "perm_label"):
            listen_ok, ctrl_ok = permission_state()
            self.perm_input.configure(
                text=f"输入监控（监听按键）：{'✅ 已授权' if listen_ok else '❌ 未授权'}",
                fg=TEXT if listen_ok else "#FF3B30")
            self.perm_ctrl.configure(
                text=f"辅助功能（拦截按键）：{'✅ 已授权' if ctrl_ok else '❌ 未授权'}",
                fg=TEXT if ctrl_ok else "#FF3B30")
            self.perm_label.configure(
                text="媒体键监听：" + ("已启用" if capture else "未启用（授权后重启客户端）")
                + f"\n程序：{'ClearCall200.app' if getattr(sys, 'frozen', False) else 'python -m clearcall200'}"
                + f"\npyobjc：{'可用' if _pyobjc_ok() else '不可用'}")
        if hasattr(self, "capture_label"):
            self.capture_label.configure(
                text="采集通道（媒体键事件）：" + ("已启用" if capture else "未启用，需辅助功能权限"))

        counts = getattr(self.app, "trigger_counts", {})
        for trig, lbl in getattr(self, "stat_rows", {}).items():
            lbl.configure(text=str(counts.get(trig, 0)))

    # ---------------- 入口 ----------------
    def loop(self) -> None:
        self._refresh_status()
        self.root.mainloop()

    def selftest(self, ms: int = 900) -> None:
        self.root.after(300, lambda: self._show_page("连接"))
        self.root.after(500, lambda: self._show_page("按键"))
        self.root.after(ms, self._quit_all)
        self.root.mainloop()


def permission_state() -> tuple[bool, bool]:
    try:
        import Quartz
        return bool(Quartz.CGPreflightListenEventAccess()), bool(Quartz.CGPreflightPostEventAccess())
    except Exception:
        return False, False


def request_permissions() -> None:
    try:
        import Quartz
        Quartz.CGRequestListenEventAccess()
        Quartz.CGRequestPostEventAccess()
    except Exception:
        pass


def asset_path(rel: str) -> str:
    """资源定位：开发态按仓库根，PyInstaller 打包态按 _MEIPASS。"""
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", "."), rel)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel)


def _pyobjc_ok() -> bool:
    try:
        from .mac_input import available
        return available()
    except Exception:
        return False


def bluetooth_devices() -> list[dict]:
    """读取本机蓝牙设备（macOS system_profiler）。"""
    try:
        out = subprocess.run(["system_profiler", "SPBluetoothDataType"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    devices: list[dict] = []
    section = None
    cur = None
    for raw in out.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.endswith(":") and ("Connected" in stripped or "连接" in stripped):
            section = "connected" if ("Connected" in stripped and "Not" not in stripped) or "已连接" in stripped else "not"
            continue
        if section is None or not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= 10 and stripped.endswith(":"):
            cur = {"name": stripped[:-1], "connected": section == "connected",
                   "address": "", "battery": ""}
            devices.append(cur)
        elif cur is not None and stripped.startswith("Address:"):
            cur["address"] = stripped.split(":", 1)[1].strip()
        elif cur is not None and stripped.startswith("Battery Level:"):
            cur["battery"] = stripped.split(":", 1)[1].strip()
    return devices
