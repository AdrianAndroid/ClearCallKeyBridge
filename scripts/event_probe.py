"""事件探针（开发诊断用）：把所有非鼠标事件原样打出来，用于判断耳机按键到底有没有进系统事件流。

用法：python3 scripts/event_probe.py 60     # 监听 60 秒
输出每行：type / subtype / code / state，其中 NX_SYSDEFINED(14) 的 code 就是 NX_KEYTYPE_*。
"""
import sys
import time

import Quartz
from AppKit import NSEvent


IGNORE_TYPES = {
    Quartz.kCGEventNull, Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDragged,
    Quartz.kCGEventRightMouseDragged, Quartz.kCGEventOtherMouseDragged,
    Quartz.kCGEventScrollWheel, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp,
    Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp,
    Quartz.kCGEventFlagsChanged, Quartz.kCGEventTapDisabledByTimeout,
    Quartz.kCGEventTapDisabledByUserInput,
}


def main(seconds: int = 60) -> int:
    t0 = time.monotonic()

    def cb(proxy, etype, event, refcon):
        if etype in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            Quartz.CGEventTapEnable(tap, True)
            print(f"{time.monotonic()-t0:6.2f}  TAP-DISABLED-REENABLED", flush=True)
            return event
        if etype in IGNORE_TYPES:
            return event
        ns = NSEvent.eventWithCGEvent_(event)
        sub = ns.subtype() if ns else -1
        code = state = -1
        if etype == 14 and ns is not None:  # NX_SYSDEFINED
            d = ns.data1()
            code = (d & 0xFFFF0000) >> 16
            state = (d & 0xFF00) >> 8
        else:
            code = ns.keyCode() if ns else -1
        print(f"{time.monotonic()-t0:6.2f}  type={etype:<3} subtype={sub:<2} code={code:<4} state={state}",
              flush=True)
        return event

    mask = Quartz.kCGEventMaskForAllEvents
    taps = []
    for loc, name in ((Quartz.kCGHIDEventTap, "HID"), (Quartz.kCGSessionEventTap, "SESSION")):
        def cb2(proxy, etype, event, refcon, _name=name):
            if etype in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
                return event
            if etype in IGNORE_TYPES:
                return event
            ns = NSEvent.eventWithCGEvent_(event)
            sub = ns.subtype() if ns else -1
            code = state = -1
            if etype == 14 and ns is not None:
                d = ns.data1()
                code = (d & 0xFFFF0000) >> 16
                state = (d & 0xFF00) >> 8
            else:
                code = ns.keyCode() if ns else -1
            print(f"{time.monotonic()-t0:6.2f}  [{_name}] type={etype:<3} subtype={sub:<2} code={code:<4} state={state}", flush=True)
            return event
        tp = Quartz.CGEventTapCreate(loc, Quartz.kCGHeadInsertEventTap,
                                     Quartz.kCGEventTapOptionDefault, mask, cb2, None)
        if tp:
            taps.append((tp, name))
            print(f"OK {name} tap created", flush=True)
    if not taps:
        print("ERR 无法创建事件监听（缺输入监控权限）", flush=True)
        return 2
    loop = Quartz.CFRunLoopGetCurrent()
    for tp, _ in taps:
        src = Quartz.CFMachPortCreateRunLoopSource(None, tp, 0)
        Quartz.CFRunLoopAddSource(loop, src, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tp, True)
    print(f"OK 监听 {seconds}s，请按耳机按键…", flush=True)
    try:
        Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, seconds, False)
    finally:
        for tp, _ in taps:
            Quartz.CGEventTapEnable(tp, False)
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 60))
