"""macOS 媒体键采集（耳机 AVRCP 按键的系统侧投影）。

为什么是这个方案：
  macOS 不提供 AVRCP / HFP 的公共 API，但系统会把耳机按键**投影成媒体键事件**
  （NX_SYSDEFINED，subtype=8 AUX_CONTROL_BUTTONS）。用 CGEventTap 监听这些事件
  就能拿到按下 / 松开边沿——这正好对应 parser 需要的 press / release。
  默认**拦截**（回调返回 None → 事件被吞掉，系统不再调音量 / 不再播放暂停）；
  拦截只针对已识别的 4 个耳机键，键盘亮度等其它系统定义键仍原样放行。

权限：需要在「系统设置 → 隐私与安全性 → 辅助功能 / 输入监控」里允许运行本程序的终端。
     没有权限时 CGEventTapCreate 返回 None，这里会抛出 PermissionError 并给出指引。
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

try:
    import Quartz
    from AppKit import NSEvent
    _AVAILABLE = True
except Exception:  # pyobjc 缺失（非 macOS 或未装）
    Quartz = None
    NSEvent = None
    _AVAILABLE = False

NX_SYSDEFINED = 14
SUBTYPE_AUX = 8
STATE_DOWN = 0x0A
STATE_UP = 0x0B

# NX_KEYTYPE_* → 我们的物理键名
KEYMAP = {
    0: "volp",    # NX_KEYTYPE_SOUND_UP
    1: "volm",    # NX_KEYTYPE_SOUND_DOWN
    7: "mute",    # NX_KEYTYPE_MUTE
    16: "call",   # NX_KEYTYPE_PLAY（通话键在 macOS 侧通常表现为播放/接听）
    3: None,      # BRIGHTNESS_UP
    4: None,      # BRIGHTNESS_DOWN
    17: None,     # NEXT
    18: None,     # PREVIOUS
}

GUIDE = (
    "需要在「系统设置 → 隐私与安全性 → 辅助功能」里勾选运行本程序的终端"
    "（若仍不行，再到「输入监控」里勾一次），然后重新启动。"
)


def available() -> bool:
    return _AVAILABLE


class MediaKeySource:
    """在后台线程里跑 CFRunLoop，把媒体键边沿转成 press / release 回调。"""

    def __init__(self, on_edge: Callable[[str, str], None], intercept: bool = True):
        self.on_edge = on_edge
        self.intercept = intercept          # True=吞掉事件（真拦截）；False=旁听并存
        self._tap = None
        self._loop = None
        self._thread: Optional[threading.Thread] = None
        self.error: Optional[str] = None

    def start(self) -> bool:
        if not _AVAILABLE:
            self.error = "pyobjc(Quartz/AppKit) 不可用"
            return False
        mask = Quartz.CGEventMaskBit(NX_SYSDEFINED)
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            self._callback,
            None,
        )
        if not self._tap:
            self.error = "无法创建事件监听（缺辅助功能/输入监控权限）"
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def _run(self) -> None:
        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._loop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        Quartz.CFRunLoopRun()

    def stop(self) -> None:
        if self._loop and Quartz:
            Quartz.CFRunLoopStop(self._loop)
        self._tap = None

    def _callback(self, proxy, etype, event, refcon):
        if etype in (Quartz.kCGEventTapDisabledByTimeout,
                     Quartz.kCGEventTapDisabledByUserInput):
            Quartz.CGEventTapEnable(self._tap, True)
            return event
        try:
            ns = NSEvent.eventWithCGEvent_(event)
            if ns is None or ns.subtype() != SUBTYPE_AUX:
                return event
            data1 = ns.data1()
            code = (data1 & 0xFFFF0000) >> 16
            state = (data1 & 0xFF00) >> 8
            key = KEYMAP.get(code)
            if key:
                kind = "press" if state == STATE_DOWN else "release"
                self.on_edge(kind, key)
                if self.intercept:
                    return None   # 吞掉事件：系统音量/播放行为不再发生
        except Exception:
            pass
        return event   # 未识别的系统定义键（亮度等）照常放行


def probe(seconds: int = 60, out=print) -> int:
    """探针：打印每个边沿，用于确认耳机按键到键名的映射。"""
    if not available():
        out("ERR pyobjc(Quartz/AppKit) 不可用")
        return 2

    def on_edge(kind: str, key: str) -> None:
        out(f"EDGE {kind:<7} key={key}  t={time.monotonic():.3f}")

    src = MediaKeySource(on_edge)
    if not src.start():
        out(f"ERR {src.error}")
        out(GUIDE)
        return 3
    out(f"OK listening {seconds}s — 请按耳机上的 静音 / 通话 / 音量+ / 音量−")
    try:
        time.sleep(seconds)
    finally:
        src.stop()
    out("DONE probe")
    return 0
