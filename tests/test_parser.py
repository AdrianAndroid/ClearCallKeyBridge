"""手势解析的时序验收（对应 device-input spec 的手势判定与时延条款）。"""
from __future__ import annotations

import unittest

from clearcall200.parser import GestureParser


def make_parser(double_bound: bool = True, call_state: str = "idle", learn: bool = False):
    return GestureParser(
        long_press_ms=1500,
        double_click_ms=500,
        debounce_ms=50,
        double_bound=lambda: double_bound,
        call_state=lambda: call_state,
        learn_mode=lambda: learn,
    )


def triggers(events):
    return [e[1] for e in events if e[0] == "trigger"]


class TestLongPress(unittest.TestCase):
    def test_long_fires_at_threshold_without_click(self):
        p = make_parser()
        p.press("call", 0.0)
        self.assertEqual(triggers(p.tick(1.2)), [])          # 未到阈值
        self.assertEqual(triggers(p.tick(1.5)), ["call:long"])  # 到达阈值立即触发
        self.assertEqual(triggers(p.release("call", 1.9)), [])  # 释放不再产 click

    def test_release_after_threshold_emits_long(self):
        p = make_parser()
        p.press("volp", 0.0)
        self.assertEqual(triggers(p.release("volp", 2.0)), ["volp:long"])


class TestClickAndDouble(unittest.TestCase):
    def test_click_immediate_when_double_not_bound(self):
        p = make_parser(double_bound=False)
        p.press("call", 0.0)
        self.assertEqual(triggers(p.release("call", 0.2)), ["call:click"])

    def test_click_waits_window_when_double_bound(self):
        p = make_parser(double_bound=True)
        p.press("call", 0.0)
        self.assertEqual(triggers(p.release("call", 0.2)), [])   # 挂起等窗口
        self.assertEqual(triggers(p.tick(0.5)), [])              # 窗口未结束
        self.assertEqual(triggers(p.tick(0.8)), ["call:click"])  # 窗口过期 -> click

    def test_double_click(self):
        p = make_parser(double_bound=True)
        p.press("call", 0.0)
        p.release("call", 0.2)
        p.press("call", 0.4)      # 距上次 release 0.2s，在 0.5s 窗口内
        self.assertEqual(triggers(p.release("call", 0.55)), ["call:double"])

    def test_two_far_clicks_are_two_singles(self):
        p = make_parser(double_bound=True)
        p.press("call", 0.0)
        p.release("call", 0.2)
        self.assertEqual(triggers(p.tick(1.0)), ["call:click"])
        p.press("call", 2.0)
        p.release("call", 2.2)
        self.assertEqual(triggers(p.tick(3.0)), ["call:click"])

    def test_learn_mode_always_waits_window(self):
        p = make_parser(double_bound=False, learn=True)
        p.press("call", 0.0)
        self.assertEqual(triggers(p.release("call", 0.2)), [])
        self.assertEqual(triggers(p.tick(0.8)), ["call:click"])


class TestVolumeKeys(unittest.TestCase):
    def test_volp_click(self):
        p = make_parser()
        p.press("volp", 0.0)
        self.assertEqual(triggers(p.release("volp", 0.3)), ["volp:click"])

    def test_volm_click_only(self):
        p = make_parser()
        p.press("volm", 0.0)
        self.assertEqual(triggers(p.release("volm", 1.8)), ["volm:click"])


class TestMuteHardwareLimit(unittest.TestCase):
    def test_mute_idle_produces_nothing(self):
        p = make_parser(call_state="idle")
        p.press("mute", 0.0)
        self.assertEqual(triggers(p.release("mute", 0.2)), [])

    def test_mute_in_call_produces_click(self):
        p = make_parser(call_state="active")
        p.press("mute", 0.0)
        self.assertEqual(triggers(p.release("mute", 0.2)), ["mute:click"])


class TestEdges(unittest.TestCase):
    def test_edges_are_emitted(self):
        p = make_parser()
        self.assertEqual(p.press("volp", 0.0), [("edge", "press", "volp")])
        self.assertEqual(p.release("volp", 0.2)[0], ("edge", "release", "volp"))

    def test_release_all_for_disconnect(self):
        p = make_parser()
        p.press("call", 0.0)
        events = p.release_all(0.3)
        self.assertIn(("edge", "release", "call"), events)
        self.assertEqual(p.is_pressed("call"), False)

    def test_debounce_drops_bounce(self):
        p = make_parser()
        p.press("volp", 0.0)
        self.assertEqual(p.press("volp", 0.02), [])  # 20ms 内重复按下被丢弃


if __name__ == "__main__":
    unittest.main()
