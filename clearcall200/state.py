"""全局状态模型。

规范：openspec/specs/state-model/spec.md
字段命名必须与 spec 一致，不允许在这里自造新名字。
"""
from __future__ import annotations

import time

# 允许取值，供校验与界面渲染使用
APP_MODES = ("normal", "learn")
CALL_STATES = ("idle", "ringing", "active", "held", "dialing")
PTT_MODES = ("toggle", "hold")

CALL_LABELS = {
    "idle": "IDLE",
    "ringing": "RING",
    "active": "ACTIVE",
    "held": "HELD",
    "dialing": "DIAL",
}


class State:
    """程序运行期的单一状态容器。

    任何字段变化都会让 `dirty` 置位，UI 据此决定是否重绘；
    相同的值重复写入不会产生事件（避免日志刷屏）。
    """

    def __init__(self, learn_timeout_sec: int = 30):
        self.app_mode = "normal"
        self.call_state = "idle"
        self.mic_mute = 0
        self.ptt_state = 0
        self.ptt_mode = "toggle"
        self.device_online = False
        self.busylight_capable = False
        self.learn_timeout_sec = int(learn_timeout_sec)
        self.learn_deadline = 0.0  # monotonic 时间戳；0 表示未在倒计时
        self.changed = True  # 首次渲染需要画一次

    # ---- 读取 ----
    @property
    def learn_remain(self) -> int:
        if self.app_mode != "learn" or self.learn_deadline <= 0:
            return 0
        return max(0, int(round(self.learn_deadline - time.monotonic())))

    def is_learn(self) -> bool:
        return self.app_mode == "learn"

    def call_label(self) -> str:
        return CALL_LABELS.get(self.call_state, "IDLE")

    # ---- 写入 ----
    def update(self, **kwargs) -> list[str]:
        """批量更新状态，返回发生变化的字段名列表。

        只允许更新已存在的字段，防止拼错字段名悄悄产生新属性。
        """
        changed = []
        for key, value in kwargs.items():
            if not hasattr(self, key):
                raise AttributeError(f"unknown state field: {key}")
            if getattr(self, key) != value:
                setattr(self, key, value)
                changed.append(key)
        if changed:
            self.changed = True
        return changed

    def force_learn_off(self) -> None:
        self.app_mode = "normal"
        self.learn_deadline = 0.0
        self.changed = True

    def state_line(self) -> str:
        """`state` 命令与 STATE 推送共用的行格式。"""
        return (
            f"STATE call_state={self.call_state} mic_mute={self.mic_mute} "
            f"ptt_state={self.ptt_state} ptt_mode={self.ptt_mode} "
            f"mode={self.app_mode} device_online={int(self.device_online)}"
        )
