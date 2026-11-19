"""doctor 自检（批 1 只实现不依赖蓝牙/权限的项，其余标"未探测"）。

规范：openspec/specs/runtime-ops/spec.md（运行环境自检）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

OK = "✅"
WARN = "⚠️"
FAIL = "❌"


def _probe_uinput() -> str:
    """/dev/uinput 是否可写（Linux 才有意义）。"""
    if not sys.platform.startswith("linux"):
        return f"{WARN} not linux (当前平台不支持 uinput)"
    dev = Path("/dev/uinput")
    if not dev.exists():
        return f"{FAIL} /dev/uinput 不存在\n     └ 修复：sudo modprobe uinput"
    if not os.access(dev, os.W_OK):
        return (
            f"{FAIL} permission denied\n"
            "     └ 修复：sudo usermod -aG input $USER && 重新登录\n"
            '            或 udev: KERNEL=="uinput", GROUP="input", MODE="0660"'
        )
    return f"{OK} writable"


def build_doctor_lines(state, runtime, cfg: dict, config_status: str, config_path: Path) -> list[str]:
    """生成 doctor 的整段输出。"""
    lines: list[str] = []
    lines.append("=" * 61)
    lines.append(" doctor — 环境自检")
    lines.append("=" * 61)

    # 配置
    if config_status == "recovered":
        lines.append(f" [0] config file              {WARN} 已损坏，已备份并回退默认")
        lines.append(f"     └ 原文件备份：{config_path}.bak")
    else:
        lines.append(f" [0] config file              {OK} {config_path} ({config_status})")

    # 蓝牙相关：批 1 未接入采集，如实标未探测
    lines.append(f" [1] bluetooth service        {WARN} 未探测（批 2 接入）")
    lines.append(f" [2] adapter present          {WARN} 未探测（批 2 接入）")
    online = f"在线" if state.device_online else "离线（批 2 接入前固定离线）"
    lines.append(f" [3] target device            {WARN} {cfg.get('device', '-')} {online}")
    lines.append(f" [4] hfp/avrcp reachable      {WARN} 未探测（批 2 接入）")

    # uinput：可判断的平台项
    lines.append(f" [5] /dev/uinput writable     {_probe_uinput()}")

    lines.append(f" [6] virtual mic device       {WARN} 未探测（批 3 接入）")

    obs = cfg.get("actions", {}).get("obs", {})
    lines.append(
        f" [7] obs websocket            {WARN} 未探测（批 3 接入，"
        f"配置 {obs.get('host', '-')}:{obs.get('port', '-')}）"
    )

    capable = "支持" if state.busylight_capable else "未知（待探测）"
    lines.append(f" [8] busylight capable        {WARN} {capable}")

    lock_state = "held" if runtime._locked else "not held"
    lines.append(f" [9] single instance lock     {OK} {runtime._lock_file} ({lock_state})")

    lines.append("-" * 61)
    lines.append(" 结论：批 1 阶段蓝牙/权限类项均为未探测；已完成配置与实例锁检查。")
    lines.append(" 下一步：批 2 接入采集后，[1]~[4]、[8] 才会给出真实结论。")
    lines.append("=" * 61)
    return lines
