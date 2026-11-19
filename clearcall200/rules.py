"""规则表：trigger -> action 的映射、校验与持久化。

规范：openspec/specs/key-mapping/spec.md
注意：MVP 一条 trigger 只允许绑定一个 action；action 集合封闭（见 CLAUDE.md §5）。
"""
from __future__ import annotations

import re
from typing import Optional

# 7 条固定触发源，序号与 spec 一一对应，顺序不可变（命令 set N 依赖它）
TRIGGER_ITEMS: list[tuple[str, str]] = [
    ("mute:click", "(HFP, only in call)"),
    ("call:click", ""),
    ("call:long", ""),
    ("call:double", ""),
    ("volp:click", ""),
    ("volp:long", ""),
    ("volm:click", ""),
]

TRIGGERS = [t for t, _ in TRIGGER_ITEMS]

# 物理按键 -> 支持的手势（供 parser 判定，不依赖具体规则）
KEY_GESTURES = {
    "mute": {"click"},
    "call": {"click", "long", "double"},
    "volp": {"click", "long"},
    "volm": {"click"},
}

# 单一动作（无参数）
SIMPLE_ACTIONS = ("ptt_toggle", "ptt_hold", "obs_toggle_mute", "none")

_HID_RE = re.compile(r"^hid_send\s+([A-Za-z][A-Za-z0-9]{1,7})$")
_NOTIFY_RE = re.compile(r'^notify["“](.+?)["”]$')


class ActionError(ValueError):
    """动作表达式非法。"""


def parse_action(text: str) -> str:
    """校验并规范化动作表达式，非法时抛 ActionError。

    合法形式：
      ptt_toggle | ptt_hold | obs_toggle_mute | none
      hid_send <KEY>
      notify"文本"
    """
    if not isinstance(text, str):
        raise ActionError("action must be a string")
    s = text.strip()
    if not s:
        raise ActionError("empty action")
    if s in SIMPLE_ACTIONS:
        return s
    m = _HID_RE.match(s)
    if m:
        return f"hid_send {m.group(1)}"
    m = _NOTIFY_RE.match(s)
    if m:
        return f'notify"{m.group(1)}"'
    raise ActionError(f"unknown action: {text}")


def action_kind(action: str) -> str:
    """从动作表达式取动作名（hid_send F13 -> hid_send）。"""
    return action.split(" ", 1)[0].split('"', 1)[0]


class RuleSet:
    """内存规则表 + 与配置文件的同步。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.dirty = False
        self.rules = self._normalize(cfg.get("rules", []))

    # ---- 构造 / 规范化 ----
    @staticmethod
    def _normalize(raw_rules: list) -> list[dict]:
        """以 spec 的 7 条固定触发源为准重建规则表，容忍配置里的顺序错乱。"""
        by_index: dict[int, dict] = {}
        for item in raw_rules or []:
            try:
                idx = int(item.get("index"))
                trigger = str(item.get("trigger", ""))
                action = str(item.get("action", "none"))
                if idx not in range(len(TRIGGERS)) or TRIGGERS[idx] != trigger:
                    continue
                by_index[idx] = {"index": idx, "trigger": trigger, "action": action}
            except Exception:
                continue

        normalized = []
        for i, trigger in enumerate(TRIGGERS):
            item = by_index.get(i) or {"index": i, "trigger": trigger, "action": "none"}
            # 校验动作；非法则降级为 none，避免坏配置让程序起不来
            try:
                item["action"] = parse_action(item["action"])
            except ActionError:
                item["action"] = "none"
            normalized.append(item)
        return normalized

    # ---- 查询 ----
    def get(self, index: int) -> Optional[dict]:
        if 0 <= index < len(self.rules):
            return self.rules[index]
        return None

    def trigger_at(self, index: int) -> Optional[str]:
        return TRIGGERS[index] if 0 <= index < len(TRIGGERS) else None

    def action_for_trigger(self, trigger: str) -> str:
        idx = TRIGGERS.index(trigger) if trigger in TRIGGERS else -1
        if idx < 0:
            return "none"
        return self.rules[idx]["action"]

    def double_bound(self) -> bool:
        """call:double 是否被启用（决定单击要不要等双击窗口）。"""
        return self.action_for_trigger("call:double") != "none"

    def is_long_key(self, key: str) -> bool:
        return "long" in KEY_GESTURES.get(key, set())

    # ---- 修改 ----
    def set_action(self, index: int, action_text: str) -> None:
        """修改某条规则，非法动作或越界序号抛异常，规则保持原值。"""
        if not 0 <= index < len(self.rules):
            raise IndexError(f"index out of range (0-{len(self.rules) - 1})")
        normalized = parse_action(action_text)
        if self.rules[index]["action"] != normalized:
            self.rules[index]["action"] = normalized
            self.dirty = True

    # ---- 持久化 ----
    def to_config_rules(self) -> list[dict]:
        out = []
        for item in self.rules:
            row = {"index": item["index"], "trigger": item["trigger"], "action": item["action"]}
            out.append(row)
        return out

    def apply_to(self, cfg: dict) -> None:
        cfg["rules"] = self.to_config_rules()

    def mark_saved(self) -> None:
        self.dirty = False
