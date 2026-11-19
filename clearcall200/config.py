"""配置加载与持久化。

规范：openspec/specs/key-mapping/spec.md（配置文件格式）、
     openspec/specs/runtime-ops/spec.md（配置外部变更）。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

# 默认配置：与 config/rules.example.json 保持一致
DEFAULT_CONFIG: dict = {
    "version": 1,
    "device": "E8:AA:BB:CC:DD:EE",
    "timing": {"long_press_ms": 1500, "double_click_ms": 500, "debounce_ms": 50},
    "learn_timeout_sec": 30,
    "ptt_hold_max_sec": 120,
    "ui": {"timestamp": True, "feed_max_lines": 200, "show_latency_hint": True},
    "capture": {
        "intercept": True,   # True=拦截耳机按键系统行为；False=旁听
        # V98 只读日志检测通道（openspec/changes/2026-11-19-v98-log-detect.md）
        "v98_log": {"enabled": False, "address": ""},   # address 缺省回退 device 字段
    },
    # V98 只有 3 个物理键、只支持单击：界面与默认规则一一对应（见 openspec/changes/2026-11-19-v98-single-click-only.md）
    "rules": [
        # index 对应 rules.py 的 7 条固定触发源顺序（call:click=1 / volp:click=4 / volm:click=6）
        {"index": 1, "trigger": "call:click", "action": 'hid_send F13'},
        {"index": 4, "trigger": "volp:click", "action": 'hid_send F14'},
        {"index": 6, "trigger": "volm:click", "action": 'notify"音量减"'},
    ],
    "actions": {
        "ptt": {"source": "default"},
        "obs": {"host": "127.0.0.1", "port": 4455, "password": ""},
        "volume_rollback": {"enabled": False},
    },
}


def default_config() -> dict:
    """返回一份默认配置的深拷贝（避免调用方改动全局常量）。"""
    return copy.deepcopy(DEFAULT_CONFIG)


def _merge_defaults(cfg: dict) -> dict:
    """把缺失的顶层字段补上默认值，容忍手写配置漏字段。"""
    base = default_config()
    for key, val in base.items():
        if key not in cfg:
            cfg[key] = val
        elif isinstance(val, dict) and isinstance(cfg.get(key), dict):
            for sub_key, sub_val in val.items():
                cfg[key].setdefault(sub_key, sub_val)
    return cfg


def load_config(path: Path) -> tuple[dict, str]:
    """加载配置。

    返回 (cfg, status)，status 取值：
      - "loaded"     正常读取
      - "generated"  文件不存在，写入默认配置
      - "recovered"  文件损坏，备份为 .bak 后回退默认
    """
    path = Path(path)
    if not path.exists():
        cfg = default_config()
        save_config(path, cfg)
        return cfg, "generated"

    try:
        raw = path.read_text(encoding="utf-8")
        cfg = json.loads(raw)
        if not isinstance(cfg, dict) or "rules" not in cfg:
            raise ValueError("配置缺少 rules 字段")
    except Exception:
        # 损坏：备份后回退默认（不静默丢用户文件）
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            path.replace(backup)
        except Exception:
            pass
        cfg = default_config()
        save_config(path, cfg)
        return cfg, "recovered"

    return _merge_defaults(cfg), "loaded"


def save_config(path: Path, cfg: dict) -> None:
    """原子写入配置文件（先写临时文件再替换，避免半截文件）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
