"""挂件纯逻辑测试：不依赖 Tk 窗口，可在无显示环境跑。"""
import unittest

from clearcall200.widget import (
    gesture_label,
    key_of_trigger,
    ptt_ratio,
    toast_text,
)


class TestTriggerMapping(unittest.TestCase):
    def test_key_of_trigger(self):
        self.assertEqual(key_of_trigger("call:double"), "call")
        self.assertEqual(key_of_trigger("volp:click"), "volp")
        self.assertEqual(key_of_trigger("mute:click"), "mute")

    def test_labels_cover_all_seven(self):
        cases = {
            "mute:click": "静音",
            "call:click": "单击",
            "call:long": "长按",
            "call:double": "双击",
            "volp:click": "音量+",
            "volp:long": "长按",
            "volm:click": "音量−",
        }
        for trigger, expect in cases.items():
            self.assertEqual(gesture_label(trigger), expect, trigger)

    def test_unknown_trigger_passthrough(self):
        self.assertEqual(gesture_label("call:triple"), "call:triple")

    def test_toast_is_short(self):
        self.assertEqual(toast_text("call:long"), "话·长按")
        self.assertEqual(toast_text("mute:click"), "静·静音")
        # 工具条宽度固定，短标签不得超过 6 个字符
        for t in ("mute:click", "call:double", "volp:long", "volm:click"):
            self.assertLessEqual(len(toast_text(t)), 6, t)


class TestPttProgress(unittest.TestCase):
    def test_zero_and_full(self):
        self.assertEqual(ptt_ratio(0, 120), 0.0)
        self.assertEqual(ptt_ratio(120, 120), 1.0)

    def test_clamped(self):
        self.assertEqual(ptt_ratio(-1, 120), 0.0)
        self.assertEqual(ptt_ratio(999, 120), 1.0)

    def test_guard_zero_max(self):
        self.assertEqual(ptt_ratio(10, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
