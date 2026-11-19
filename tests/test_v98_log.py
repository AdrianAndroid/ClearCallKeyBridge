"""V98 只读日志检测：消息解析、地址过滤、状态机基本行为。

规范：openspec/changes/2026-11-19-v98-log-detect.md
实测消息样例：docs/V98按键监听交接.md
"""
import unittest

from clearcall200.v98_log import (
    V98LogWatcher,
    build_predicate,
    parse_log_line,
    valid_address,
)

TARGET = "41:42:DF:39:9A:BE"

PLAY_LINE = (
    "2026-11-19 13:38:53.411 Df bluetoothd[181:edc] "
    "[com.apple.bluetooth:Server.Remote] "
    "Received AVRCP Play command from device 41:42:DF:39:9A:BE"
)
PAUSE_LINE = (
    "2026-11-19 13:38:51.413 Df bluetoothd[181:edc] "
    "[com.apple.bluetooth:Server.Remote] "
    "Received AVRCP Pause command from device 41:42:DF:39:9A:BE"
)
VOL_LINE = (
    "2026-11-19 13:38:50.411 Df bluetoothd[181:edc] "
    "[com.apple.bluetooth:Server.Remote] "
    "Received notification for absolute volume 0x2c (~34%) "
    "from device 41:42:DF:39:9A:BE"
)


class TestParseLogLine(unittest.TestCase):
    def test_play_command(self):
        self.assertEqual(parse_log_line(PLAY_LINE, TARGET), ("play",))

    def test_pause_command(self):
        self.assertEqual(parse_log_line(PAUSE_LINE, TARGET), ("pause",))

    def test_absolute_volume(self):
        self.assertEqual(parse_log_line(VOL_LINE, TARGET), ("volume", "0x2c", 34))

    def test_wrong_device_ignored(self):
        other = VOL_LINE.replace("41:42:DF:39:9A:BE", "AA:BB:CC:DD:EE:FF")
        self.assertIsNone(parse_log_line(other, TARGET))

    def test_unrelated_line_ignored(self):
        # 实测中同地址也会出现的 HIDShim 消息必须被忽略
        hid = (
            "2026-11-19 13:38:14.197 Df bluetoothd[181:51d45ed] "
            "[com.apple.bluetooth:Server.Core] isHIDShimDevice: HIDShim "
            "device 41:42:DF:39:9A:BE -- vID = 0x05AC, pID = 0x0220"
        )
        self.assertIsNone(parse_log_line(hid, TARGET))

    def test_empty_and_none(self):
        self.assertIsNone(parse_log_line("", TARGET))
        self.assertIsNone(parse_log_line(PLAY_LINE[:-5], TARGET))  # 地址被截断

    def test_case_insensitive_address(self):
        lower = VOL_LINE.upper().replace("0X2C", "0x2C")
        self.assertEqual(parse_log_line(lower, TARGET.lower()), ("volume", "0x2c", 34))


class TestAddressAndPredicate(unittest.TestCase):
    def test_valid_address(self):
        self.assertTrue(valid_address("41:42:DF:39:9A:BE"))
        self.assertTrue(valid_address("e8:aa:bb:cc:dd:ee"))

    def test_invalid_address(self):
        for bad in ("", "E8:AA:BB:CC:DD", "E8AABBCCDDEE", "E8:AA:BB:CC:DD:ZZ", None, 123):
            self.assertFalse(valid_address(bad))

    def test_predicate_contains_address(self):
        pred = build_predicate(TARGET)
        self.assertIn(TARGET, pred)
        self.assertIn("bluetoothd", pred)


class TestWatcherLifecycle(unittest.TestCase):
    def test_initial_status_disabled(self):
        w = V98LogWatcher(TARGET)
        self.assertEqual(w.status, "disabled")
        self.assertEqual(w.drain(), [])
        w.stop()  # 未 start 也能安全 stop

    def test_invalid_address_unavailable(self):
        w = V98LogWatcher("not-an-address")
        status = w.start()
        self.assertTrue(status.startswith("unavailable"))
        self.assertEqual(w.status, status)

    def test_stop_is_idempotent(self):
        w = V98LogWatcher(TARGET)
        w.stop()
        w.stop()
        self.assertEqual(w.status, "disabled")


if __name__ == "__main__":
    unittest.main()
