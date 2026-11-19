"""ASCII 终端界面：分区渲染、事件流环形缓冲、非 TTY 降级。

规范：openspec/specs/terminal-ui/spec.md
原型：docs/界面设计.md
"""
from __future__ import annotations

import sys
import time
from collections import deque

from .rules import TRIGGER_ITEMS
from .state import State

SEP_THIN = "-" * 61
SEP_THICK = "=" * 61
FEED_VISIBLE = 10  # 帧内可见行数（缓冲区仍是 200 行，完整内容用 export feed 导出）


class TerminalUI:
    def __init__(self, timestamp: bool = True, max_lines: int = 200, log_sink=None,
                 capture=None):
        self.feed: deque[str] = deque(maxlen=max_lines)
        self.timestamp = timestamp
        self.log_sink = log_sink          # runtime.write_log 回调
        self.capture = capture            # 图形挂件等替代输出端；为 None 时按终端规则输出
        self.interactive = sys.stdout.isatty()
        self.dirty = True
        self._last_draw = 0.0

    # ---------- 事件流 ----------
    def append(self, text: str) -> None:
        if not text:
            return
        stamp = time.strftime("%H:%M:%S") if self.timestamp else ""
        line = f"[{stamp}] {text}" if stamp else text
        self.feed.append(line)
        if self.log_sink:
            self.log_sink(line)
        if self.capture is not None:
            self.capture(line)            # 挂件形态：交给 GUI 显示，不写 stdout
        elif not self.interactive:
            # 非 TTY：逐行纯文本，可直接 grep
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        self.dirty = True

    def append_many(self, texts: list[str]) -> None:
        for t in texts:
            self.append(t)

    # ---------- 帧 ----------
    def build_frame(self, state: State, rules, buffer: str = "", debug: bool = False) -> str:
        lines: list[str] = []
        lines.append(SEP_THICK)
        lines.append(" ClearCall200 Client | follow OpenSpec")
        lines.append(SEP_THICK)
        lines.append(self._status_bar(state))
        if state.is_learn():
            lines.append(
                f" ⚠️ LEARN MODE ACTIVE: 按键只会检测、不执行动作 | {state.learn_remain}s auto exit"
            )
        elif not state.device_online and state.is_learn() is False:
            lines.append(" ⚠ BT: OFFLINE (批2接入前固定离线) — 仅 test 命令可用")
        lines.append(SEP_THIN)
        lines.append(" Bindable Triggers:")
        for i, (trg, note) in enumerate(TRIGGER_ITEMS):
            suffix = f"      {note}" if note else ""
            lines.append(f" [{i}] {trg}{suffix}")
        lines.append(SEP_THIN)
        title = " Rules (bypassed):" if state.is_learn() else " Rules:"
        lines.append(title)
        for r in rules.rules:
            lines.append(f" {r['index']}: {r['trigger']:<16} → {self._action_label(r['action'])}")
        lines.append(SEP_THIN)
        header = " Feed [LEARN DETECT]:" if state.is_learn() else " Feed:"
        if debug:
            header += "  (debug on)"
        lines.append(header)
        visible = list(self.feed)[-FEED_VISIBLE:]
        if not visible:
            lines.append(" (空)")
        else:
            hidden = len(self.feed) - len(visible)
            if hidden > 0:
                lines.append(f" (... {hidden} earlier lines, 用 export feed 查看)")
            lines.extend(visible)
        lines.append(SEP_THIN)
        lines.append(" Commands: list | set N ACTION | learn | normal | test TRIG | save | reload")
        lines.append("           state | doctor | debug on|off | export feed | help | quit")
        lines.append("> " + buffer)
        return "\n".join(lines)

    def render(self, state: State, rules, buffer: str = "", debug: bool = False) -> None:
        if not self.interactive:
            return
        now = time.monotonic()
        # ≤10Hz 合并刷新
        if not self.dirty and now - self._last_draw < 0.1:
            return
        frame = self.build_frame(state, rules, buffer, debug)
        sys.stdout.write("\x1b[H" + frame + "\x1b[J")
        sys.stdout.flush()
        self.dirty = False
        self._last_draw = now

    # ---------- 辅助 ----------
    @staticmethod
    def _status_bar(state: State) -> str:
        mic = "MUTED" if state.mic_mute else "OPEN"
        if state.ptt_state:
            ptt = f"ON·{state.ptt_mode}"
        else:
            ptt = "OFF"
        mode = "LEARN" if state.is_learn() else "NORMAL"
        return f" 📞 CALL: [{state.call_label()}] | MIC: [{mic}] | PTT: [{ptt}] | MODE:[{mode}]"

    @staticmethod
    def _action_label(action: str) -> str:
        return action if action else "none"
