"""规则表与动作校验的验收（对应 key-mapping spec）。"""
from __future__ import annotations

import unittest

from clearcall200.config import default_config
from clearcall200.rules import ActionError, RuleSet, parse_action


class TestParseAction(unittest.TestCase):
    def test_simple_actions(self):
        for text in ("ptt_toggle", "ptt_hold", "obs_toggle_mute", "none"):
            self.assertEqual(parse_action(text), text)

    def test_hid_send(self):
        self.assertEqual(parse_action("hid_send F13"), "hid_send F13")
        self.assertEqual(parse_action("  hid_send f14  "), "hid_send f14")

    def test_notify_with_quotes(self):
        self.assertEqual(parse_action('notify"长按通话键"'), 'notify"长按通话键"')
        self.assertEqual(parse_action("notify“音量减”"), 'notify"音量减"')

    def test_invalid(self):
        for text in ("", "xxx_invalid", "hid_send", "hid_send 123", 'notify""', "shell ls"):
            with self.assertRaises(ActionError):
                parse_action(text)


class TestRuleSet(unittest.TestCase):
    def setUp(self):
        self.cfg = default_config()
        self.rules = RuleSet(self.cfg)

    def test_seven_fixed_triggers(self):
        self.assertEqual(len(self.rules.rules), 7)
        self.assertEqual(self.rules.rules[0]["trigger"], "mute:click")
        self.assertEqual(self.rules.rules[6]["trigger"], "volm:click")

    def test_set_action_updates_and_marks_dirty(self):
        self.rules.set_action(5, "ptt_toggle")
        self.assertEqual(self.rules.rules[5]["action"], "ptt_toggle")
        self.assertTrue(self.rules.dirty)

    def test_set_out_of_range(self):
        with self.assertRaises(IndexError):
            self.rules.set_action(9, 'notify"x"')

    def test_set_invalid_action_keeps_original(self):
        before = self.rules.rules[3]["action"]
        with self.assertRaises(ActionError):
            self.rules.set_action(3, "xxx_invalid")
        self.assertEqual(self.rules.rules[3]["action"], before)

    def test_double_bound_toggle(self):
        self.assertTrue(self.rules.double_bound())
        self.rules.set_action(3, "none")
        self.assertFalse(self.rules.double_bound())

    def test_action_for_unknown_trigger(self):
        self.assertEqual(self.rules.action_for_trigger("nope"), "none")

    def test_normalize_ignores_broken_rows(self):
        cfg = default_config()
        cfg["rules"] = [
            {"index": 0, "trigger": "wrong:trigger", "action": "ptt_toggle"},
            {"index": 9, "trigger": "call:click", "action": "ptt_toggle"},
            {"index": 2, "trigger": "call:long", "action": "xxx_invalid"},
        ]
        rules = RuleSet(cfg)
        self.assertEqual(rules.rules[0]["action"], "none")   # 序号/trigger 不匹配被丢弃
        self.assertEqual(rules.rules[2]["action"], "none")   # 非法动作降级为 none
        self.assertEqual(len(rules.rules), 7)


if __name__ == "__main__":
    unittest.main()
