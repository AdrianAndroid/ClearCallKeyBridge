"""命令行入口：python -m clearcall200 [--config PATH] [--log PATH]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app import App


def _default_log() -> str | None:
    if getattr(sys, "frozen", False):
        p = Path.home() / "Library" / "Logs" / "ClearCall200.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)
    return None


def _default_config() -> str:
    """打成 .app 后不再依赖启动目录，配置落到用户目录。"""
    if getattr(sys, "frozen", False):
        base = Path.home() / "Library" / "Application Support" / "ClearCall200"
        base.mkdir(parents=True, exist_ok=True)
        return str(base / "rules.json")
    return "config/rules.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clearcall200",
        description="漫步者 ClearCall200 话务耳机按键自定义客户端（单体终端程序）",
    )
    parser.add_argument("--config", default=_default_config(), help="配置文件路径")
    parser.add_argument("--log", default=_default_log(), help="把事件流写入该文件")
    parser.add_argument(
        "--keyprobe", nargs="?", const=45, type=int, default=None,
        help="macOS 媒体键探针：监听 N 秒并打印耳机按键边沿（默认 45s），用于确认键位映射",
    )
    parser.add_argument(
        "--frame", nargs="?", const="normal", default=None,
        choices=["normal", "active", "learn"],
        help="只打印一帧界面（normal/active/learn），用于截图与布局自测",
    )
    parser.add_argument(
        "--ui", action="store_true",
        help="主设置窗口（配置按键）+ 常驻键位工具条，关闭主窗口只隐藏、进程保活",
    )
    parser.add_argument(
        "--ui-pet", action="store_true",
        help="主设置窗口 + 桌宠形态挂件",
    )
    parser.add_argument(
        "--ui-demo", action="store_true",
        help="演示模式：每 1.5s 轮流注入识别（挂件点亮、事件流滚动），用于演示与截图",
    )
    parser.add_argument(
        "--ui-selftest", action="store_true",
        help="主窗口自测：约 0.7s 后自动关闭",
    )
    parser.add_argument(
        "--widget", default=None, choices=["bar", "pet"],
        help="常驻置顶桌面挂件形态：bar=极小键位工具条（320×46），pet=桌宠（88×88）",
    )
    parser.add_argument(
        "--widget-demo", action="store_true",
        help="挂件演示模式：每 1.2s 轮流注入一次识别，用于演示与截图",
    )
    parser.add_argument(
        "--widget-selftest", nargs="?", const="bar", default=None,
        choices=["bar", "pet"],
        help="构造挂件后约 400ms 自动关闭，用于验证 GUI 能拉起",
    )
    args = parser.parse_args(argv)

    if args.keyprobe:
        from .mac_input import probe
        return probe(args.keyprobe)

    app = App(args.config, args.log)
    try:
        if args.frame:
            print(app.demo_frame(args.frame))
            return 0
        if args.widget_selftest:
            from .widget import build_widget
            w = build_widget(app, args.widget_selftest)
            print(f"OK widget {args.widget_selftest} built")
            # 注入 4 次识别，验证"点亮 + 徽标 + 状态刷新"整条链路不抛异常
            demo = ["call:click", "call:long", "volp:long", "mute:click"]
            for i, trig in enumerate(demo):
                w.root.after(90 * (i + 1),
                             lambda t=trig: (w.on_trigger(t), app._handle_trigger(t, "selftest")))
            w.root.after(700, lambda: print("OK widget feedback path exercised"))
            w.selftest(900)
            return 0
        if args.widget and args.widget_demo:
            from .widget import build_widget
            w = build_widget(app, args.widget)
            app.attach_media_keys()
            app.edge_listener = w.on_edge
            app.trigger_listener = w.on_trigger
            app.ui.capture = lambda line: None
            app.ui.interactive = False
            demo = ["call:click", "call:long", "volp:long", "mute:click", "call:double", "volm:click"]
            def _demo(i=0):
                trig = demo[i % len(demo)]
                app._handle_trigger(trig, "demo")
                w.root.after(1200, lambda: _demo(i + 1))
            w.root.after(200, _demo)
            try:
                w.loop()
            finally:
                app._cleanup()
            return 0
        if args.ui_selftest:
            from .ui_gui import DesktopClient
            app.attach_media_keys()
            client = DesktopClient(app, "bar")
            print(f"OK desktop client built (media_keys={'on' if app.media_keys_ok else 'off'})")
            client.selftest()
            return 0
        if args.ui_demo:
            from .ui_gui import DesktopClient
            app.attach_media_keys()
            client = DesktopClient(app, "bar", demo=True)
            app.rt.install_signals()
            try:
                client.loop()
            finally:
                app._cleanup()
            return 0
        if args.ui_pet:
            return app.run(mode="ui-pet")
        if args.ui:
            return app.run(mode="ui")
        return app.run(mode=args.widget or "cli")
    finally:
        if app.state.ptt_state:
            app.state.update(ptt_state=0)
        app.rt.release_lock()


if __name__ == "__main__":
    sys.exit(main())
