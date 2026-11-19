"""应用编排：命令解析、事件分发、两种运行模式（交互 / 管道）。

批 1 不接蓝牙：所有按键事件由 `test trigger=...` 注入。
"""
from __future__ import annotations

import queue
import select
import sys
import time
from pathlib import Path

from .actions import Executor
from .config import load_config, save_config
from .diag import build_doctor_lines
from .parser import GestureParser
from .rules import TRIGGERS, ActionError, RuleSet
from .runtime import Runtime
from .state import State
from .ui import TerminalUI
from .v98_log import V98LogWatcher

EXPORT_PATH = Path("feed-export.txt")


class App:
    def __init__(self, config_path: str | Path, log_path: str | None = None,
                 v98_log: bool = False):
        self.config_path = Path(config_path)
        self.rt = Runtime(log_path)

        ok, msg = self.rt.acquire_lock()
        if not ok:
            print(f"> ERR {msg}", file=sys.stderr)
            raise SystemExit(2)

        self.cfg, self.config_status = load_config(self.config_path)
        self.state = State(int(self.cfg.get("learn_timeout_sec", 30)))
        self.rules = RuleSet(self.cfg)
        self.executor = Executor(self.state)

        log_err = self.rt.attach_log()
        ui_cfg = self.cfg.get("ui", {})
        self.ui = TerminalUI(
            timestamp=bool(ui_cfg.get("timestamp", True)),
            max_lines=int(ui_cfg.get("feed_max_lines", 200)),
            log_sink=self.rt.write_log,
        )
        self.show_latency_hint = bool(ui_cfg.get("show_latency_hint", True))

        timing = self.cfg.get("timing", {})
        self.parser = GestureParser(
            long_press_ms=int(timing.get("long_press_ms", 1500)),
            double_click_ms=int(timing.get("double_click_ms", 500)),
            debounce_ms=int(timing.get("debounce_ms", 50)),
            double_bound=self.rules.double_bound,
            call_state=lambda: self.state.call_state,
            learn_mode=lambda: self.state.is_learn(),
        )

        self.debug = False
        self.quit = False
        self._reader = None
        self.detected: set[str] = set()
        self.unknown = 0
        self.trigger_counts = {t: 0 for t in TRIGGERS}

        # macOS 媒体键采集（耳机按键 → 边沿）
        self.media_source = None
        self.media_keys_ok = False
        self.intercept_on = False
        self.perm_granted_before = False

        # 音量键探测（耳机音量键不走事件流，只能靠观测音量变化）
        self.vol_watcher = None
        self._vol_last_key = None
        self._vol_last_ts = 0.0
        self._edge_q: queue.Queue = queue.Queue()

        # V98 只读日志检测（详见 openspec/changes/2026-11-19-v98-log-detect.md）
        self.v98_requested = bool(v98_log)
        self.v98_watcher: V98LogWatcher | None = None

        # 挂件回调挂点（None 时完全不影响终端行为）
        self.edge_listener = None    # f(kind, key)：press/release 边沿
        self.trigger_listener = None  # f(trigger)：识别结果

        self._startup_lines(log_err)

    # ---------------- 启动信息 ----------------
    def _startup_lines(self, log_err: str | None) -> None:
        if self.config_status == "generated":
            self.ui.append(f"OK 已生成默认配置 {self.config_path}")
        elif self.config_status == "recovered":
            self.ui.append(f"ERR 配置损坏，已备份为 {self.config_path}.bak 并回退默认")
        if log_err:
            self.ui.append(f"ERR log disabled: {log_err}")

    # ---------------- 入口 ----------------
    def run(self, mode: str = "cli") -> int:
        if mode in ("ui", "ui-pet"):
            self._run_desktop("pet" if mode == "ui-pet" else "bar")
            return 0
        if mode in ("bar", "pet"):
            self._run_widget(mode)
            return 0
        if sys.stdin.isatty() and sys.stdout.isatty():
            self._run_interactive()
        else:
            self._run_piped()
        return 0

    # ---------------- 桌面客户端（主设置窗口 + 挂件） ----------------
    def _run_desktop(self, widget_mode: str) -> None:
        from .ui_gui import DesktopClient

        client = DesktopClient(self, widget_mode)
        self.attach_media_keys()
        self.attach_volume_watch()
        self.attach_v98_log()
        self.rt.install_signals()
        try:
            client.loop()
        finally:
            self._cleanup()

    # ---------------- 挂件模式（常驻置顶浮层） ----------------
    def _run_widget(self, mode: str) -> None:
        from .widget import build_widget

        widget = build_widget(self, mode)
        self.edge_listener = widget.on_edge
        self.trigger_listener = widget.on_trigger
        self.ui.capture = lambda line: None   # 事件流交给挂件，不污染 stdout
        self.ui.interactive = False
        self.attach_media_keys()
        self.attach_volume_watch()
        self.attach_v98_log()
        self.rt.install_signals()
        try:
            widget.loop()
        finally:
            self._cleanup()

    # ---------------- 管道模式（非 TTY，逐行命令） ----------------
    def _run_piped(self) -> None:
        for raw in sys.stdin:
            if self.quit:
                break
            self._execute(raw.strip())

    # ---------------- 交互模式 ----------------
    def _run_interactive(self) -> None:
        buffer = ""
        reader = _CharReader()
        reader.start()
        self.rt.install_signals()
        self.attach_v98_log()
        self.ui.render(self.state, self.rules)
        try:
            while not self.quit and not self.rt.stop_requested:
                tick_events = self.parser.tick(time.monotonic())
                self._dispatch_parser_events(tick_events)
                self._housekeeping()
                self.pump_v98_log()

                if reader.wait(0.05):
                    ch = reader.read()
                    if ch == "\x03":  # Ctrl-C
                        self.rt.stop_requested = True
                        break
                    if ch == "\r":
                        self.ui.append("> " + buffer) if buffer else None
                        self._execute(buffer)
                        buffer = ""
                    elif ch in ("\x7f", "\b"):
                        buffer = buffer[:-1]
                    elif ch and ch.isprintable():
                        buffer += ch
                self.ui.render(self.state, self.rules, buffer, self.debug)
        finally:
            reader.stop()
            self._cleanup()
            if self.rt.stop_requested and not self.quit:
                sys.stdout.write("\n")

    # ---------------- 静态预览（无需 TTY，用于检查布局 / 截图） ----------------
    def demo_frame(self, mode: str = "normal") -> str:
        """打印一帧界面文本，用于文档截图与布局自测。"""
        if mode == "learn":
            self.state.update(app_mode="learn", call_state="active", mic_mute=0)
            self.state.learn_deadline = time.monotonic() + 12
            self.ui.feed.clear()
            for line in (
                "EVENT trigger=call:click",
                "[LEARN ✅] trigger=call:click        → BusyLight blink ✨ (waited double window)",
                "EVENT trigger=call:long",
                "[LEARN ✅] trigger=call:long         → BusyLight blink ✨",
                "EVENT trigger=volp:long",
                "[LEARN ✅] trigger=volp:long         → BusyLight blink ✨",
                "[LEARN ⚠] unknown pdu: cid=0x0041 op=0x7c",
                "EVENT trigger=volm:click",
                "[LEARN ✅] trigger=volm:click        → BusyLight control unsupported",
            ):
                self.ui.feed.append(line)
        elif mode == "active":
            self.state.update(call_state="active", ptt_state=1, ptt_mode="hold", device_online=True)
            self.ui.feed.clear()
            for line in (
                "STATE call_state=ringing mic_mute=0",
                "STATE call_state=active mic_mute=0",
                "EVENT trigger=volp:long",
                "ACTION action=ptt_hold (placeholder: 待批3，由 edge press/release 驱动)",
                "EVENT trigger=mute:click",
                "ACTION action=obs_toggle_mute (placeholder: 待批3 OBS WebSocket)",
                "STATE call_state=active mic_mute=1",
            ):
                self.ui.feed.append(line)
        return self.ui.build_frame(self.state, self.rules)


    def _execute(self, line: str) -> None:
        if not line:
            if not self.ui.interactive:
                pass
            return
        parts = line.split(None, 2)
        cmd = parts[0].lower()

        if cmd in ("quit", "exit"):
            self.ui.append("OK bye")
            self.quit = True
        elif cmd == "help":
            self._cmd_help()
        elif cmd == "list":
            self._cmd_list()
        elif cmd == "set":
            self._cmd_set(line)
        elif cmd == "learn":
            self._cmd_learn()
        elif cmd == "normal":
            self._cmd_normal("manual")
        elif cmd == "test":
            self._cmd_test(line)
        elif cmd == "save":
            self._cmd_save()
        elif cmd == "reload":
            self._cmd_reload(line)
        elif cmd == "state":
            self.ui.append(self.state.state_line())
        elif cmd == "doctor":
            self.ui.append_many(build_doctor_lines(
                self.state, self.rt, self.cfg, self.config_status, self.config_path))
        elif cmd == "debug":
            self._cmd_debug(line)
        elif cmd == "export":
            self._cmd_export(line)
        else:
            self.ui.append(f"ERR unknown command: {cmd}（help 查看命令）")

    def _cmd_help(self) -> None:
        self.ui.append_many([
            "Commands:",
            "  list                打印当前全部规则",
            "  set N ACTION        改写第 N 号触发源绑定（如 set 5 ptt_hold，set 3 none 关闭双击）",
            "  learn / normal      进入 / 退出学习模式",
            "  test trigger=X      手动模拟触发（如 test trigger=volp:long）",
            "  save                规则写入配置文件",
            "  reload [force]      重新读取配置（dirty 时需 force）",
            "  state               打印当前状态",
            "  doctor              环境自检",
            "  debug on|off        原始报文摘要开关（批 2 起有数据）",
            "  export feed         导出最近事件流到 feed-export.txt",
            "  help / quit",
        ])

    def _cmd_list(self) -> None:
        for r in self.rules.rules:
            self.ui.append(f"RULE {r['index']} {r['trigger']} → {r['action']}")

    def _cmd_set(self, line: str) -> None:
        parts = line.split(None, 2)
        if len(parts) < 3:
            self.ui.append("ERR usage: set N ACTION")
            return
        try:
            index = int(parts[1])
        except ValueError:
            self.ui.append("ERR index must be a number (0-6)")
            return
        action_text = parts[2].strip()
        try:
            self.rules.set_action(index, action_text)
        except IndexError as exc:
            self.ui.append(f"ERR {exc}")
            return
        except ActionError as exc:
            self.ui.append(f"ERR {exc}")
            return
        self.ui.append(
            f"OK rule {index} ({TRIGGERS[index]}) → {self.rules.rules[index]['action']}"
            + ("  dirty=true (输入 save 生效)" if self.rules.dirty else "")
        )

    def _cmd_learn(self) -> None:
        if self.state.is_learn():
            self.state.learn_deadline = time.monotonic() + self.state.learn_timeout_sec
            self.ui.append(f"OK learn timer reset ({self.state.learn_timeout_sec}s)")
            return
        self.state.update(app_mode="learn")
        self.state.learn_deadline = time.monotonic() + self.state.learn_timeout_sec
        self.detected.clear()
        self.unknown = 0
        self.ui.append(f"MODE learn ({self.state.learn_timeout_sec}s auto exit)")

    def _cmd_normal(self, reason: str) -> None:
        if not self.state.is_learn():
            self.ui.append("OK already normal")
            return
        self.state.force_learn_off()
        summary = f" (detected={len(self.detected)}/{len(TRIGGERS)}"
        if self.unknown:
            summary += f", unknown={self.unknown}"
        summary += ")"
        self.ui.append(f"MODE normal ({reason}){summary}")

    def _cmd_test(self, line: str) -> None:
        token = line.split(None, 1)[1].strip() if len(line.split(None, 1)) > 1 else ""
        if token.startswith("trigger="):
            token = token.split("=", 1)[1]
        if token not in TRIGGERS:
            self.ui.append(f"ERR unknown trigger: {token}（可用：{', '.join(TRIGGERS)}）")
            return
        if self.debug:
            self.ui.append(f"[DBG] test inject trigger={token}")
        if token == "mute:click" and self.state.call_state == "idle":
            self.ui.append("DBG 注意: mute:click 仅通话中耳机才上报，空闲按该键真机不会有事件")
        self._handle_trigger(token, source="test")

    def _cmd_save(self) -> None:
        self.rules.apply_to(self.cfg)
        try:
            save_config(self.config_path, self.cfg)
        except Exception as exc:
            self.ui.append(f"ERR save failed: {exc}")
            return
        self.rules.mark_saved()
        self.ui.append(f"OK saved to {self.config_path} dirty=false")

    def _cmd_reload(self, line: str) -> None:
        force = "force" in line.split()
        if self.rules.dirty and not force:
            self.ui.append("ERR unsaved changes (dirty=true)；用 save 保存，或 reload force 丢弃")
            return
        cfg, status = load_config(self.config_path)
        self.cfg = cfg
        self.rules = RuleSet(cfg)
        self.state.learn_timeout_sec = int(cfg.get("learn_timeout_sec", 30))
        timing = cfg.get("timing", {})
        self.parser = GestureParser(
            long_press_ms=int(timing.get("long_press_ms", 1500)),
            double_click_ms=int(timing.get("double_click_ms", 500)),
            debounce_ms=int(timing.get("debounce_ms", 50)),
            double_bound=self.rules.double_bound,
            call_state=lambda: self.state.call_state,
            learn_mode=lambda: self.state.is_learn(),
        )
        self.ui.append(f"OK reloaded ({status})")

    def _cmd_debug(self, line: str) -> None:
        parts = line.split()
        if len(parts) < 2 or parts[1] not in ("on", "off"):
            self.ui.append("ERR usage: debug on|off")
            return
        self.debug = parts[1] == "on"
        self.ui.append(f"OK debug={parts[1]}")

    def _cmd_export(self, line: str) -> None:
        parts = line.split()
        if len(parts) < 2 or parts[1] != "feed":
            self.ui.append("ERR usage: export feed")
            return
        try:
            EXPORT_PATH.write_text("\n".join(self.ui.feed) + "\n", encoding="utf-8")
            self.ui.append(f"OK exported {len(self.ui.feed)} lines to {EXPORT_PATH.resolve()}")
        except Exception as exc:
            self.ui.append(f"ERR export failed: {exc}")

    # ---------------- 事件 ----------------
    # ---------------- macOS 媒体键采集 ----------------
    def attach_media_keys(self) -> bool:
        """设备来源无法确认时禁止启用全局媒体键监听。"""
        self.media_keys_ok = False
        self.intercept_on = False
        self.ui.append("INFO 全局媒体键监听已关闭（V98 按键由只读日志通道采集）")
        return False

    def stop_media_keys(self) -> None:
        if self.media_source:
            self.media_source.stop()
            self.media_source = None
        self.media_keys_ok = False

    def attach_volume_watch(self) -> bool:
        """系统音量变化无法可靠归因到 V98，不监听也不回写。"""
        self.vol_watcher = None
        return False

    # ---------------- V98 只读日志检测 ----------------
    def attach_v98_log(self) -> str:
        """按配置启动 V98 日志检测；只读旁听，不进规则匹配。

        状态来源：--v98-log（会话级强制）或 capture.v98_log.enabled；
        地址取 capture.v98_log.address，缺省回退 device 字段。
        返回并展示最终状态，启动失败必须如实显示 unavailable。
        """
        self.stop_v98_log()
        section = self.cfg.get("capture", {}).get("v98_log", {}) or {}
        enabled = self.v98_requested or bool(section.get("enabled", False))
        if not enabled:
            self.ui.append("WARN V98 日志检测未启用（--v98-log / capture.v98_log.enabled）")
            return "disabled"
        address = str(section.get("address") or self.cfg.get("device") or "").upper()
        watcher = V98LogWatcher(address)
        watcher.start()
        self.v98_watcher = watcher
        if watcher.status == "running":
            self.ui.append(f"OK V98 日志检测启动 addr={address}（只读旁听）")
        elif watcher.status == "starting":
            self.ui.append(f"OK V98 日志检测启动中 addr={address}")
        else:
            self.ui.append(f"ERR V98 log detect unavailable: {watcher.status.split(':', 1)[-1]}")
        return watcher.status

    def stop_v98_log(self) -> None:
        if self.v98_watcher:
            self.v98_watcher.stop()
            self.v98_watcher = None

    def pump_v98_log(self) -> None:
        """把日志检测事件刷进事件流（必须在主线程调用）。

        只展示原始检测事件，不做方向判定、不触发 trigger / 动作；
        音量通知的同值重复与交错如实打印。
        """
        if not self.v98_watcher:
            return
        import time as _t

        for ev in self.v98_watcher.drain():
            now = _t.monotonic()
            if ev[0] == "play":
                self.ui.append("DETECT v98 play (AVRCP Play)")
                if now - getattr(self, "_v98_play_ts", 0.0) >= 0.15:
                    self._v98_play_ts = now
                    self._handle_trigger("call:click", "v98")
            elif ev[0] == "pause":
                self.ui.append("DETECT v98 pause (AVRCP Pause)")
                # 播放/暂停是同一个物理键：与 Play 共用去重时间戳，映射到同一张卡
                if now - getattr(self, "_v98_play_ts", 0.0) >= 0.15:
                    self._v98_play_ts = now
                    self._handle_trigger("call:click", "v98")
            elif ev[0] == "volume":
                key = self._v98_volume_dir(ev[2], now)
                self.ui.append(f"DETECT v98 volume={ev[1]} (~{ev[2]}%) -> {key}")
                if key:
                    self._handle_trigger(f"{key}:click", "v98")

    def _v98_volume_dir(self, pct: int, now: float) -> str | None:
        """绝对音量百分比 → volp / volm（方向判定，含边界重发处理）。

        规则见 openspec/changes/2026-11-19-v98-triggers.md：
        - 首次通知只记基线，不出方向；
        - 上升 ≥1 → volp；下降 ≥1 → volm；
        - 同值重复：距上次触发 ≥0.25s 时沿用上一次方向，否则丢弃。
        """
        last_pct = getattr(self, "_v98_vol_pct", None)
        last_dir = getattr(self, "_v98_vol_dir", None)
        last_ts = getattr(self, "_v98_vol_ts", 0.0)

        if last_pct is None:
            self._v98_vol_pct = pct
            return None

        if pct > last_pct:
            key = "volp"
        elif pct < last_pct:
            key = "volm"
        else:
            # 同值：只有边界才有意义——100% 只可能是"加到顶"，0% 只可能是"减到底"
            if pct == 100 and now - last_ts >= 0.25:
                key = "volp"
            elif pct == 0 and now - last_ts >= 0.25:
                key = "volm"
            else:
                # 中间值重复：视为抖动/重发，丢弃
                return None
            self._v98_vol_ts = now
            self._v98_vol_pct = pct
            self._v98_vol_dir = key
            return key

        self._v98_vol_pct = pct
        self._v98_vol_dir = key
        self._v98_vol_ts = now
        return key

    def pump_volume(self) -> None:
        """轮询音量变化 → 识别为 volp/volm 按键（必须在主线程调用）。"""
        if not self.vol_watcher or not hasattr(self, "_vol_queue"):
            return
        items = []
        while True:
            try:
                items.append(self._vol_queue.get_nowait())
            except Exception:
                break
        for key, ts in items:
            # 耳机音量键只做单击判定（长按在 macOS 侧没有可识别的连续事件）
            self._vol_last_key, self._vol_last_ts = key, ts
            if key == "unknown":
                # 方向无法判定：两个音量卡片都点亮，事件记为 vol?:click
                if self.edge_listener:
                    self.edge_listener("press", "volp")
                    self.edge_listener("release", "volp")
                    self.edge_listener("press", "volm")
                    self.edge_listener("release", "volm")
                self.ui.append("EVENT trigger=vol?:click (方向未知)")
                return
            trig = f"{key}:click"
            if self.edge_listener:
                self.edge_listener("press", key)
                self.edge_listener("release", key)
            self.ui.append(f"EVENT trigger={trig} (volume-key)")
            self._handle_trigger(trig, "volume")

    def pump_edges(self) -> None:
        """把采集线程的边沿喂给解析器（必须在主线程调用）。"""
        now = time.monotonic()
        while True:
            try:
                kind, key = self._edge_q.get_nowait()
            except queue.Empty:
                break
            if kind == "press":
                self.parser.press(key, now)
            elif kind == "release":
                self.parser.release(key, now)
            else:
                continue
            if self.edge_listener:
                self.edge_listener(kind, key)

    def _dispatch_parser_events(self, events) -> None:
        for ev in events:
            if ev[0] == "edge":
                # 边沿事件不进 UI 事件流：挂件用于点亮，批 3 的 ptt_hold 用于起停
                if self.edge_listener:
                    self.edge_listener(ev[1], ev[2])
                continue
            if ev[0] == "trigger":
                self._handle_trigger(ev[1], source="hw")

    def _handle_trigger(self, trigger: str, source: str) -> None:
        self.trigger_counts[trigger] = self.trigger_counts.get(trigger, 0) + 1
        if self.trigger_listener:
            self.trigger_listener(trigger)
        self.ui.append(f"EVENT trigger={trigger}")
        if self.state.is_learn():
            self.detected.add(trigger)
            hint = ""
            if (self.show_latency_hint and trigger.endswith(":click")
                    and self.rules.double_bound() and trigger.startswith("call")):
                hint = " (waited double window)"
            suffix = "BusyLight blink ✨" if self.state.busylight_capable else "BusyLight control unsupported"
            self.ui.append(f"[LEARN ✅] trigger={trigger:<18} → {suffix}{hint}")
            return
        action = self.rules.action_for_trigger(trigger)
        if action == "none":
            return  # 未绑定：静默，不产生噪音
        line = self.executor.execute(action)
        if line:
            self.ui.append(line)

    # ---------------- 杂项 ----------------
    def _housekeeping(self) -> None:
        if self.state.is_learn() and self.state.learn_remain <= 0:
            self._cmd_normal("learn timeout")

    def _cleanup(self) -> None:
        self.stop_media_keys()
        self.stop_v98_log()
        # 停推流（批 1 无音频，仅复位状态）→ 释放锁
        if self.state.ptt_state:
            self.state.update(ptt_state=0)
        self.rt.release_lock()


class _CharReader:
    """交互模式下的逐字符读取（cbreak），以便倒计时与事件推进不被 input() 阻塞。"""

    def __init__(self):
        self.fd = sys.stdin.fileno()
        self._old = None
        self._enabled = False

    def start(self) -> None:
        try:
            import termios
            import tty
            self._old = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
            self._enabled = True
        except Exception:
            self._enabled = False

    def stop(self) -> None:
        if not self._enabled or not self._old:
            return
        try:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old)
        except Exception:
            pass
        self._enabled = False

    def wait(self, timeout: float) -> bool:
        r, _, _ = select.select([self.fd], [], [], timeout)
        return bool(r)

    def read(self) -> str:
        import os
        data = os.read(self.fd, 1)
        if not data:
            return "\x03"
        return data.decode("utf-8", errors="ignore")
