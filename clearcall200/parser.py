"""按键时序解析：原始按下/松开 -> 标准 trigger + 内部边沿事件。

规范：openspec/specs/device-input/spec.md（手势判定与时延 / 边沿事件）
设计要点：
  - 长按在**到达阈值时**立即判定（由 tick 驱动），不等释放；
  - 单击是否要等双击窗口，取决于 call:double 是否被绑定；
  - mute:click 只在通话状态非 idle 时成立（硬件事实，不伪造）；
  - 边沿事件供 ptt_hold 使用，不进入 UI 事件流。

所有方法都接收显式时间戳（monotonic 秒），便于用测试注入确定性时序。
"""
from __future__ import annotations

from typing import Callable

KEYS = ("mute", "call", "volp", "volm")

# 物理按键支持的长按 / 双击（与 rules.KEY_GESTURES 保持一致）
LONG_KEYS = {"call", "volp"}
DOUBLE_KEYS = {"call"}

# 输出事件：("trigger", "call:long") 或 ("edge", "press", "call")
Event = tuple


class GestureParser:
    def __init__(
        self,
        long_press_ms: int = 1500,
        double_click_ms: int = 500,
        debounce_ms: int = 50,
        double_bound: Callable[[], bool] = lambda: True,
        call_state: Callable[[], str] = lambda: "idle",
        learn_mode: Callable[[], bool] = lambda: False,
    ):
        self.long_ms = long_press_ms
        self.double_ms = double_click_ms
        self.debounce_ms = debounce_ms
        self._double_bound = double_bound
        self._call_state = call_state
        self._learn_mode = learn_mode

        self._press_t: dict[str, float] = {}
        self._long_fired: set[str] = set()
        self._pending_click: dict[str, float] = {}   # 等待双击窗口的单击
        self._second_press: set[str] = set()          # 本次按下是双击的第二下
        self._last_press: dict[str, float] = {}

    # ---------- 内部 ----------
    def _allow_click(self) -> bool:
        """learn 模式下按"存在 double 规则"处理：为了验证全部手势。"""
        return self._learn_mode() or self._double_bound()

    def _wait_double(self, key: str) -> bool:
        return key in DOUBLE_KEYS and self._allow_click()

    # ---------- 外部 ----------
    def press(self, key: str, t: float) -> list[Event]:
        if key not in KEYS:
            return []
        last = self._last_press.get(key)
        # 防抖：同一键极短间隔的重复报文视为抖动
        if last is not None and (t - last) * 1000 < self.debounce_ms and key in self._press_t:
            return []
        self._last_press[key] = t

        events: list[Event] = [("edge", "press", key)]

        pending = self._pending_click.pop(key, None)
        if pending is not None and (t - pending) * 1000 <= self.double_ms:
            self._second_press.add(key)
        else:
            self._second_press.discard(key)

        self._press_t[key] = t
        self._long_fired.discard(key)
        return events

    def release(self, key: str, t: float) -> list[Event]:
        if key not in KEYS:
            return []
        events: list[Event] = [("edge", "release", key)]
        start = self._press_t.pop(key, None)
        if start is None:
            return events

        # 长按已判定 -> 本次按压不再产生 click
        if key in self._long_fired:
            self._long_fired.discard(key)
            self._second_press.discard(key)
            return events

        duration_ms = (t - start) * 1000

        # 释放时才发现够长按时长（例如 tick 没被及时调用）
        if key in LONG_KEYS and duration_ms >= self.long_ms:
            events.append(("trigger", f"{key}:long"))
            self._second_press.discard(key)
            return events

        if key == "mute":
            # 只有通话中耳机才上报；这里再校验一次通话状态
            if self._call_state() != "idle":
                events.append(("trigger", "mute:click"))
            self._second_press.discard(key)
            return events

        if key == "volm":
            events.append(("trigger", "volm:click"))
            return events

        if key == "call":
            if self._wait_double(key):
                if key in self._second_press:
                    self._second_press.discard(key)
                    events.append(("trigger", "call:double"))
                else:
                    # 单击要等窗口：先挂起，由 tick 决定
                    self._pending_click[key] = t
            else:
                events.append(("trigger", "call:click"))
            return events

        if key == "volp":
            events.append(("trigger", "volp:click"))
            return events

        return events

    def tick(self, t: float) -> list[Event]:
        """周期性调用（约 50ms 一次）：判定长按与已到期的单击。"""
        events: list[Event] = []

        for key in list(self._press_t.keys()):
            if key in LONG_KEYS and key not in self._long_fired:
                if (t - self._press_t[key]) * 1000 >= self.long_ms:
                    self._long_fired.add(key)
                    events.append(("trigger", f"{key}:long"))

        for key, pending_at in list(self._pending_click.items()):
            if (t - pending_at) * 1000 >= self.double_ms:
                del self._pending_click[key]
                events.append(("trigger", f"{key}:click"))

        return events

    def release_all(self, t: float) -> list[Event]:
        """设备断连时补发释放，避免按住类动作卡住（见 spec 边沿事件）。"""
        events: list[Event] = []
        for key in list(self._press_t.keys()):
            events.extend(self.release(key, t))
        self._pending_click.clear()
        self._second_press.clear()
        return events

    def is_pressed(self, key: str) -> bool:
        return key in self._press_t
