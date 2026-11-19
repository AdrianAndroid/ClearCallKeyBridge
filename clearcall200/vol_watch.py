"""系统输出音量探测（macOS CoreAudio），用于“拦截”耳机的音量键。

实测结论（2026-11-19）：
- 耳机音量键走蓝牙 AVRCP 绝对音量，不产生任何键盘/媒体键事件，CGEventTap 抓不到；
- 但按键会让 CoreAudio 发生可观测变化：`volm` 属性瞬间报错(ERR)，同时
  `vmvc`（VirtualMainVolume，即系统 HUD 显示的那个音量）短暂变成新值，
  例如 0.6929 → 0.5681（按 −）。据此可判断“按了哪个方向”。
- 因此本模块同时读 volm 与 vmvc，任一可读即用；识别方向后立刻写回原值实现拦截。
"""
from __future__ import annotations

import ctypes
import ctypes.util
import threading
import time

_AUDIO = None
try:
    _AUDIO = ctypes.CDLL(
        ctypes.util.find_library("AudioToolbox")
        or "/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox"
    )
except Exception:
    _AUDIO = None

K_OBJECT_SYSTEM = 1
_SCOPE_OUTPUT = "outp"


class _Addr(ctypes.Structure):
    _fields_ = [("sel", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("elem", ctypes.c_uint32)]


def _fourcc(s: str) -> int:
    v = 0
    for ch in s:
        v = (v << 8) | ord(ch)
    return v


def available() -> bool:
    return _AUDIO is not None


def default_output_device() -> int:
    addr = _Addr(_fourcc("dOut"), _fourcc("glob"), 0)
    size = ctypes.c_uint32(4)
    dev = ctypes.c_uint32(0)
    st = _AUDIO.AudioObjectGetPropertyData(
        ctypes.c_uint32(K_OBJECT_SYSTEM), ctypes.byref(addr), ctypes.c_uint32(0),
        None, ctypes.byref(size), ctypes.byref(dev))
    return dev.value if st == 0 else 0


def _read(dev: int, sel: str, elem: int) -> float | None:
    addr = _Addr(_fourcc(sel), _fourcc(_SCOPE_OUTPUT), elem)
    size = ctypes.c_uint32(4)
    val = ctypes.c_float(0)
    st = _AUDIO.AudioObjectGetPropertyData(
        ctypes.c_uint32(dev), ctypes.byref(addr), ctypes.c_uint32(0),
        None, ctypes.byref(size), ctypes.byref(val))
    return float(val.value) if st == 0 else None


def _write(dev: int, sel: str, elem: int, value: float) -> bool:
    addr = _Addr(_fourcc(sel), _fourcc(_SCOPE_OUTPUT), elem)
    val = ctypes.c_float(max(0.0, min(1.0, value)))
    st = _AUDIO.AudioObjectSetPropertyData(
        ctypes.c_uint32(dev), ctypes.byref(addr), ctypes.c_uint32(0),
        None, ctypes.c_uint32(4), ctypes.byref(val))
    return st == 0


def get_volume(dev: int = 0) -> float | None:
    """读取音量：优先 volm（设备主音量），失败退 vmvc（系统虚拟音量）。"""
    if not available():
        return None
    dev = dev or default_output_device()
    for sel, elem in (("volm", 1), ("vmvc", 0), ("volm", 2)):
        v = _read(dev, sel, elem)
        if v is not None:
            return v
    return None


def set_volume(value: float, dev: int = 0) -> bool:
    if not available():
        return False
    dev = dev or default_output_device()
    for sel, elem in (("volm", 1), ("vmvc", 0), ("volm", 2)):
        if _write(dev, sel, elem, value):
            return True
    return False


class VolumeWatcher:
    """把“音量被拨动”翻译成 volp / volm 按键（识别方向后立即回滚）。

    关键点：按键瞬间 volm 会读失败，但 vmvc 仍可读且已变成新值，
    所以两个属性都要试，谁可读用谁。
    """

    def __init__(self, intercept: bool = True, step: float = 0.02, cooldown: float = 0.18,
                 debounce: float = 0.22):
        self.intercept = intercept
        self.step = step
        self.cooldown = cooldown
        self.debounce = debounce
        self._dev = 0
        self._last: float | None = None          # 基线（正常状态的音量）
        self._cooldown_until = 0.0
        self._last_event = 0.0
        self._pressed = False          # 一次按键只出一次事件
        self._readable_since = 0.0
        self._pending_restore = False

    # ------------------------------------------------------------------
    def _probe(self) -> float | None:
        if not self._dev:
            self._dev = default_output_device()
        # 顺序很关键：先用设备主音量 volm；它读不到（按键瞬间会报错）时才退到 vmvc
        for sel, elem in (("volm", 1), ("volm", 2), ("vmvc", 0)):
            v = _read(self._dev, sel, elem)
            if v is not None:
                return v
        return None

    def poll(self) -> list[tuple[str, float]]:
        if not available():
            return []
        now = time.monotonic()
        if not self._dev:
            self._dev = default_output_device()

        volm = _read(self._dev, "volm", 1)
        if volm is None:
            volm = _read(self._dev, "volm", 2)
        vmvc = _read(self._dev, "vmvc", 0)

        # 情况 A：设备主音量读不到 —— 实测这就是“耳机音量键被按下的瞬间”
        if volm is None:
            try:
                with open("/tmp/cc_vol_debug.log", "a", encoding="utf-8") as fh:
                    fh.write(f"BLIP pressed={self._pressed} vmvc={vmvc} last={self._last}\n")
            except Exception:
                pass
            self._readable_since = 0.0
            if self._pressed:
                return []
            self._pressed = True
            self._last_event = now
            return [(self._direction(vmvc), now)]

        # 主音量恢复可读：稳定一小段时间后才允许下一次按键
        if self._pressed:
            if self._readable_since == 0.0:
                self._readable_since = now
            elif now - self._readable_since > 0.04:
                self._pressed = False
                self._readable_since = 0.0
            return []
        self._readable_since = 0.0

        # 情况 B：读得到但值变了（音量真的被改）
        if self._last is None:
            self._last = volm
            return []
        delta = volm - self._last
        if abs(delta) < self.step:
            return []
        if now - self._last_event < self.debounce:
            # 同一次按键的余波
            if self.intercept and self._last is not None:
                set_volume(self._last, self._dev)
            return []
        self._last_event = now
        key = "volp" if delta > 0 else "volm"
        if self.intercept:
            set_volume(self._last, self._dev)
        self._last = volm if not self.intercept else self._last
        return [(key, now)]

    def _direction(self, vmvc: float | None) -> str:
        """判断按下的是 + 还是 −；读不出来就返回 unknown。"""
        if vmvc is None or self._last is None:
            return "unknown"
        if abs(vmvc - self._last) < self.step:
            return "unknown"
        return "volp" if vmvc > self._last else "volm"

    def start(self, emit, interval: float = 0.003) -> None:
        """后台高速轮询（10ms）——80ms 一次的界面心跳会漏掉按键瞬断。"""
        self._stop_flag = False

        def _dbg(msg):
            try:
                with open("/tmp/cc_vol_debug.log", "a", encoding="utf-8") as fh:
                    fh.write(msg + "\n")
            except Exception:
                pass

        _dbg("THREAD STARTED")

        def _loop():
            n = 0
            while not getattr(self, "_stop_flag", True):
                try:
                    for key, ts in self.poll():
                        emit(key, ts)
                except Exception as exc:          # 线程不能静默死掉
                    try:
                        with open("/tmp/cc_vol_debug.log", "a", encoding="utf-8") as fh:
                            fh.write(f"ERR {exc!r}\n")
                    except Exception:
                        pass
                n += 1
                if n % 500 == 0:
                    _dbg(f"ALIVE n={n} pressed={self._pressed} last={self._last}")
                time.sleep(interval)

        threading.Thread(target=_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop_flag = True

    def resync(self) -> None:
        self._dev = self._dev or default_output_device()
        v = self._probe()
        if v is not None:
            self._last = v
        self._pending_restore = False

# ---------------- 属性变更通知（比轮询可靠） ----------------
_LISTENER_PROTO = ctypes.CFUNCTYPE(
    ctypes.c_int32, ctypes.c_uint32, ctypes.c_uint32,
    ctypes.POINTER(_Addr), ctypes.c_void_p)


class VolumeListener:
    """注册 CoreAudio 音量属性监听：系统一改音量就回调，不怕瞬断太短。"""

    def __init__(self, on_change):
        self.on_change = on_change
        self.dev = 0
        self._callbacks = []
        self._count = 0

    def _make_cb(self):
        def _cb(obj, n_addr, addrs, refcon):
            try:
                self._count += 1
                self.on_change(obj, self._count)
            except Exception:
                pass
            return 0
        cb = _LISTENER_PROTO(_cb)
        self._callbacks.append(cb)      # 必须持引用，否则被 GC 掉会崩
        return cb

    def attach(self) -> bool:
        if not available():
            return False
        self.dev = default_output_device()
        cb = self._make_cb()
        ok = False
        for elem in (1, 2):
            addr = _Addr(_fourcc("volm"), _fourcc(_SCOPE_OUTPUT), elem)
            st = _AUDIO.AudioObjectAddPropertyListener(
                ctypes.c_uint32(self.dev), ctypes.byref(addr), cb, None)
            ok = ok or (st == 0)
        return ok

