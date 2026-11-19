"""常驻桌面挂件（极小浮层工具条 / 桌宠），Tkinter 实现，零第三方依赖。

定位：状态镜像 + 按键反馈器。不是主界面，不承载配置，不复制规则引擎逻辑。

- bar 形态：单行 320×46 工具条。连接点 · 通话缩写 · 4 键胶囊 · 识别结果 · PTT 细条
- pet 形态：88×88 角色浮层，表情随状态变化

平台说明：挂件使用普通窗口层级，不强制置顶。
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import font as tkfont

BG = "#FCFCFD"
BORDER = "#DFDFE4"
FG = "#1D1D1F"
DIM = "#86868B"
ACCENT = "#0A84FF"
WARN = "#ffb74d"
OK = "#34C759"
PILL = "#F2F2F7"
PILL_DOWN = "#0A84FF"

KEY_ORDER = ("mute", "call", "volp", "volm")
KEY_GLYPH = {"mute": "静", "call": "话", "volp": "＋", "volm": "－"}
KEY_NAME = {"mute": "静音", "call": "通话", "volp": "音量+", "volm": "音量−"}

TRIGGER_LABEL = {
    "mute:click": "静音",
    "call:click": "单击",
    "call:long": "长按",
    "call:double": "双击",
    "volp:click": "音量+",
    "volp:long": "长按",
    "volm:click": "音量−",
}

BADGE_SEC = 1.2
TICK_MS = 80


# ---------------- 纯逻辑（可单测，不依赖 Tk） ----------------
def key_of_trigger(trigger: str) -> str:
    """call:double → call"""
    return trigger.split(":", 1)[0]


def gesture_label(trigger: str) -> str:
    return TRIGGER_LABEL.get(trigger, trigger)


def toast_text(trigger: str) -> str:
    """工具条里空间有限，用短标签：话·长按"""
    return f"{KEY_GLYPH.get(key_of_trigger(trigger), '?')}·{gesture_label(trigger)}"


def ptt_ratio(elapsed_sec: float, max_sec: float) -> float:
    if max_sec <= 0:
        return 0.0
    return max(0.0, min(1.0, elapsed_sec / max_sec))


# ---------------- 基类：普通窗口 / 可拖动 ----------------
class _FloatingBase:
    def __init__(self, app, width: int, height: int, master=None):
        self.app = app
        self.width, self.height = width, height
        self._drag = (0, 0)
        self.on_closed = None          # 关闭回调（由主窗口接管时使用）

        # 与主设置窗口共用同一个 Tk root：挂件只是 Toplevel，不起第二个 Tk()
        self._own_root = master is None
        self.root = tk.Tk() if master is None else tk.Toplevel(master)
        self.root.title("ClearCall200")
        self.root.configure(bg=BG)
        # 使用普通窗口，避免无边框窗口在 macOS 上保持浮动层级。
        self.root.withdraw()
        try:
            self.root.wm_attributes("-alpha", 0.94)
        except Exception:
            pass
        self._place()
        self.root.deiconify()

        self.small = tkfont.Font(family="Menlo", size=10)
        self.tiny = tkfont.Font(family="Menlo", size=9)

        self.root.after(TICK_MS, self._tick)

    def _place(self) -> None:
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        x = max(0, sw - self.width - 24)
        self.root.geometry(f"{self.width}x{self.height}+{x}+48")

    def bind_drag(self, widget: tk.Widget) -> None:
        widget.bind("<ButtonPress-1>", self._drag_start, add="+")
        widget.bind("<B1-Motion>", self._drag_move, add="+")

    def _drag_start(self, event) -> None:
        self._drag = (event.x_root - self.root.winfo_x(),
                      event.y_root - self.root.winfo_y())

    def _drag_move(self, event) -> None:
        x = event.x_root - self._drag[0]
        y = event.y_root - self._drag[1]
        self.root.geometry(f"+{x}+{y}")

    def bind_quit(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def close(self) -> None:
        self.app.quit = True
        try:
            self.app._cleanup()
        finally:
            self.root.destroy()
        if self.on_closed:
            self.on_closed()

    # 子类实现
    def _tick(self) -> None:
        raise NotImplementedError

    def selftest(self, ms: int = 400) -> None:
        self.root.after(ms, self.root.destroy)
        self.root.mainloop()


# ---------------- 形态 1：键位工具条 ----------------
class KeyBarWidget(_FloatingBase):
    """320×46 单行工具条。"""

    W, H = 320, 46

    def __init__(self, app, master=None):
        super().__init__(app, self.W, self.H, master=master)
        self._pills: dict[str, tk.Label] = {}
        self._badge_until = 0.0
        self._press_clear_at: dict[str, float] = {}
        self._ptt_start: float | None = None
        self._learn_blink = False
        self._last_toast = ""

        outer = tk.Frame(self.root, bg=BORDER, bd=0)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=BG, bd=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.inner = inner
        self.bind_drag(inner)

        pad = tk.Frame(inner, bg=BG)
        pad.pack(fill="both", expand=True, padx=8, pady=8)
        self.bind_drag(pad)

        # 连接点
        self.dot = tk.Label(pad, text="●", bg=BG, fg=DIM, font=self.small)
        self.dot.pack(side="left")
        self.bind_drag(self.dot)

        # 通话状态缩写
        self.call = tk.Label(pad, text="IDLE", bg=BG, fg=DIM, font=self.tiny, width=4, anchor="w")
        self.call.pack(side="left", padx=(4, 6))
        self.bind_drag(self.call)

        # 4 个键位胶囊
        for key in KEY_ORDER:
            pill = tk.Label(pad, text=KEY_GLYPH[key], bg=PILL, fg=FG, font=self.small,
                            width=2, height=1, bd=0)
            pill.pack(side="left", padx=(0, 3), ipady=2)
            pill.bind("<ButtonPress-1>", lambda e, k=key: self._click_key(k), add="+")
            self.bind_drag(pill)
            self._pills[key] = pill

        # PTT 细进度条
        self.ptt_canvas = tk.Canvas(pad, width=46, height=6, bg=BG, bd=0,
                                    highlightthickness=0)
        self.ptt_canvas.pack(side="right", padx=(6, 0))
        self.bind_drag(self.ptt_canvas)

        # 识别结果（占据中间剩余空间）
        self.toast = tk.Label(pad, text="", bg=BG, fg=ACCENT, font=self.tiny, anchor="e")
        self.toast.pack(side="right", fill="x", expand=True)
        self.bind_drag(self.toast)

        # 齿轮：唤起主设置窗口（主窗口被隐藏时用它回来）
        self.on_settings = None
        self.gear = tk.Label(pad, text="⚙", bg=BG, fg=DIM, font=self.small)
        self.gear.pack(side="right", padx=(0, 6))
        self.gear.bind("<ButtonPress-1>", lambda e: self.on_settings and self.on_settings())

        self._draw_ptt(0.0, on=False)

    # ---- 事件入口（由 App 回调） ----
    def on_edge(self, kind: str, key: str) -> None:
        pill = self._pills.get(key)
        if pill is None:
            return
        if kind == "press":
            pill.configure(bg=PILL_DOWN, fg="#FFFFFF")
            self._press_clear_at.pop(key, None)
        else:
            # 松开：200ms 内回落，避免断连时卡在高亮
            self._press_clear_at[key] = time.monotonic() + 0.2
            self.root.after(200, lambda k=key: self._release_pill(k))

    def _release_pill(self, key: str) -> None:
        pill = self._pills.get(key)
        if pill is not None:
            pill.configure(bg=PILL, fg=FG)

    def on_trigger(self, trigger: str) -> None:
        """识别到 trigger：短脉冲点亮 + 显示短标签。"""
        key = key_of_trigger(trigger)
        pill = self._pills.get(key)
        if pill is not None:
            pill.configure(bg=ACCENT, fg="#FFFFFF")
            self.root.after(180, lambda k=key: self._release_pill(k))
        self._last_toast = toast_text(trigger)
        self.toast.configure(text=self._last_toast, fg=ACCENT)
        self._badge_until = time.monotonic() + BADGE_SEC

    def _click_key(self, key: str) -> None:
        """点胶囊 = 注入一次该键的 click（干跑验证用，不替代真实采集）。"""
        line = f"EVENT trigger={key}:click (widget)"
        self.app.ui.append(line)
        self.app._handle_trigger(f"{key}:click")

    # ---- 状态刷新 ----
    def _tick(self) -> None:
        if self.app.quit:
            return
        if getattr(self.app.rt, "stop_requested", False):
            self.app.quit = True
            self.root.destroy()
            return
        # 采集线程 → 解析器（必须在主线程）
        self.app.pump_edges()
        self.app.pump_volume()
        self.app.pump_v98_log()
        self.app._dispatch_parser_events(self.app.parser.tick(time.monotonic()))
        st = self.app.state
        now = time.monotonic()

        # 连接 / 学习模式指示
        learn = st.is_learn()
        if learn:
            self._learn_blink = not self._learn_blink
            self.dot.configure(fg=WARN if self._learn_blink else "#6b5326")
            self.inner.master.configure(bg=WARN)
            self.inner.configure(bg=BG)
        else:
            self.dot.configure(fg=OK if st.device_online else DIM)
            self.inner.master.configure(bg=BORDER)

        # 通话状态
        colors = {"idle": DIM, "ringing": WARN, "active": OK, "held": ACCENT, "dialing": ACCENT}
        self.call.configure(text=st.call_label().upper()[:4], fg=colors.get(st.call_state, DIM))

        # 麦克风静音：把静音胶囊染成琥珀
        mute_pill = self._pills["mute"]
        if st.mic_mute and mute_pill.cget("bg") == PILL:
            mute_pill.configure(fg=WARN)

        # 过期回落（防止 after 在极端情况下没触发）
        for key, deadline in list(self._press_clear_at.items()):
            if now >= deadline:
                self._press_clear_at.pop(key, None)
                self._release_pill(key)

        # 徽标淡出
        if self._badge_until and now >= self._badge_until:
            self._badge_until = 0.0
            self.toast.configure(text="", fg=ACCENT)

        # PTT 进度
        if st.ptt_state:
            if self._ptt_start is None:
                self._ptt_start = now
            if st.ptt_mode == "hold":
                elapsed = now - self._ptt_start
                max_sec = float(self.app.config.get("ptt_hold_max_sec", 120) or 120)
                self._draw_ptt(ptt_ratio(elapsed, max_sec), on=True)
                if not self._badge_until:
                    self.toast.configure(text=f"PTT {elapsed:.1f}s", fg=OK)
            else:
                self._draw_ptt(1.0 if self._learn_blink else 0.5, on=True)
                if not self._badge_until:
                    self.toast.configure(text="PTT ON", fg=OK)
        else:
            self._ptt_start = None
            self._draw_ptt(0.0, on=False)

        self.root.after(TICK_MS, self._tick)

    def _draw_ptt(self, ratio: float, on: bool) -> None:
        c = self.ptt_canvas
        c.delete("all")
        c.create_rectangle(0, 2, 46, 4, fill="#3a3d42", outline="")
        if on and ratio > 0:
            c.create_rectangle(0, 2, max(1, int(46 * ratio)), 4,
                               fill=ACCENT if ratio < 1.0 else WARN, outline="")

    def loop(self) -> None:
        self.root.mainloop()


# ---------------- 形态 2：桌宠 ----------------
PET_FACE = {
    "idle": ("🐰", DIM),
    "press": ("😮", ACCENT),
    "ptt": ("🎙️", OK),
    "mute": ("🤐", WARN),
    "call": ("📞", OK),
}


class PetWidget(_FloatingBase):
    """88×88 角色浮层：表情 + 一两字气泡。"""

    W, H = 88, 88

    def __init__(self, app, master=None):
        super().__init__(app, self.W, self.H, master=master)
        self._press_until = 0.0
        self._bubble_until = 0.0
        self._bounce = False

        wrap = tk.Frame(self.root, bg=BG, bd=0)
        wrap.pack(fill="both", expand=True)
        self.bind_drag(wrap)

        self.bubble = tk.Label(wrap, text="", bg=BG, fg=ACCENT, font=self.tiny,
                               anchor="center", wraplength=84)
        self.bubble.pack(fill="x", pady=(6, 0))
        self.bind_drag(self.bubble)

        self.face = tk.Label(wrap, text="🐰", bg=BG, fg=DIM, font=("Menlo", 34))
        self.face.pack(expand=True)
        self.bind_drag(self.face)

    def on_edge(self, kind: str, key: str) -> None:
        if kind == "press":
            self._press_until = time.monotonic() + 0.25

    def on_trigger(self, trigger: str) -> None:
        self.bubble.configure(text=toast_text(trigger))
        self._bubble_until = time.monotonic() + BADGE_SEC

    def _tick(self) -> None:
        if self.app.quit:
            return
        if getattr(self.app.rt, "stop_requested", False):
            self.app.quit = True
            self.root.destroy()
            return
        # 采集线程 → 解析器（必须在主线程）
        self.app.pump_edges()
        self.app.pump_volume()
        self.app.pump_v98_log()
        self.app._dispatch_parser_events(self.app.parser.tick(time.monotonic()))
        st = self.app.state
        now = time.monotonic()

        if st.ptt_state:
            face, color = PET_FACE["ptt"]
        elif st.mic_mute:
            face, color = PET_FACE["mute"]
        elif st.call_state in ("ringing", "active", "held", "dialing"):
            face, color = PET_FACE["call"]
        elif now < self._press_until:
            face, color = PET_FACE["press"]
        else:
            face, color = PET_FACE["idle"]

        self.face.configure(text=face, fg=color)
        self._bounce = not self._bounce
        self.face.pack_configure(pady=(2 if self._bounce else 0, 0))

        if self._bubble_until and now >= self._bubble_until:
            self._bubble_until = 0.0
            self.bubble.configure(text="")

        self.root.after(TICK_MS, self._tick)

    def loop(self) -> None:
        self.root.mainloop()


def build_widget(app, mode: str, master=None):
    if mode == "pet":
        return PetWidget(app, master=master)
    return KeyBarWidget(app, master=master)
