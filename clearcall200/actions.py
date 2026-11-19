"""动作执行引擎（批 1 为占位实现）。

规范：openspec/specs/action-execution/spec.md
批 1 只做两件事：校验动作名 + 输出可观测的 ACTION 行；
ptt_* 会更新内部状态（不涉及音频），其余动作只打日志，真实落地在批 3。
"""
from __future__ import annotations

from .rules import action_kind
from .state import State

PLACEHOLDER_ACTIONS = ("hid_send", "obs_toggle_mute", "notify")


class Executor:
    def __init__(self, state: State):
        self.state = state

    def execute(self, action: str) -> str:
        """执行动作，返回要写入事件流的 ACTION 行（不含前缀）。"""
        kind = action_kind(action)

        if kind == "none":
            return ""

        if kind == "ptt_toggle":
            new_state = 0 if self.state.ptt_state else 1
            if new_state and self.state.ptt_mode == "hold" and self.state.ptt_state:
                return "ACTION action=ptt_toggle → ERR ptt busy (hold active)"
            self.state.update(ptt_state=new_state, ptt_mode="toggle")
            return f"ACTION action=ptt_toggle → ptt_state={new_state} (placeholder: 无音频)"

        if kind == "ptt_hold":
            # 按住说话需要边沿事件驱动（批 3 接入音频），批 1 只记录意图
            if self.state.ptt_state and self.state.ptt_mode == "toggle":
                return "ACTION action=ptt_hold → ERR ptt busy (toggle active)"
            return "ACTION action=ptt_hold (placeholder: 待批3，由 edge press/release 驱动)"

        if kind == "hid_send":
            key = action.split(" ", 1)[1]
            return f"ACTION action=hid_send {key} (placeholder: 待批3 uinput)"

        if kind == "obs_toggle_mute":
            return "ACTION action=obs_toggle_mute (placeholder: 待批3 OBS WebSocket)"

        if kind == "notify":
            text = action[len('notify"'):-1]
            return f'ACTION action=notify "{text}" (placeholder: 待批3 桌面通知)'

        return f"ERR unknown action: {action}"
