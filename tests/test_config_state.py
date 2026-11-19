"""配置加载与状态模型的验收。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from clearcall200.config import DEFAULT_CONFIG, default_config, load_config, save_config
from clearcall200.state import State


class TestConfig(unittest.TestCase):
    def test_generate_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            cfg, status = load_config(path)
            self.assertEqual(status, "generated")
            self.assertTrue(path.exists())
            self.assertEqual(len(cfg["rules"]), 3)

    def test_load_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            save_config(path, default_config())
            cfg, status = load_config(path)
            self.assertEqual(status, "loaded")
            self.assertEqual(cfg["device"], DEFAULT_CONFIG["device"])

    def test_corrupt_file_is_backed_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            path.write_text("{not json", encoding="utf-8")
            cfg, status = load_config(path)
            self.assertEqual(status, "recovered")
            self.assertTrue(path.with_suffix(".json.bak").exists())
            self.assertEqual(len(cfg["rules"]), 3)
            json.loads(path.read_text(encoding="utf-8"))  # 回退后的文件必须合法

    def test_missing_fields_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            path.write_text(json.dumps({"device": "AA:BB", "rules": []}), encoding="utf-8")
            cfg, status = load_config(path)
            self.assertEqual(status, "loaded")
            self.assertEqual(cfg["device"], "AA:BB")
            self.assertIn("timing", cfg)          # 缺失字段被补默认
            self.assertEqual(len(cfg["rules"]), 0)


class TestState(unittest.TestCase):
    def test_defaults(self):
        s = State(30)
        self.assertEqual(s.app_mode, "normal")
        self.assertEqual(s.call_state, "idle")
        self.assertEqual(s.ptt_state, 0)
        self.assertFalse(s.device_online)

    def test_update_reports_changes_only(self):
        s = State()
        self.assertEqual(s.update(call_state="ringing"), ["call_state"])
        self.assertEqual(s.update(call_state="ringing"), [])
        self.assertEqual(s.call_label(), "RING")

    def test_unknown_field_rejected(self):
        s = State()
        with self.assertRaises(AttributeError):
            s.update(callstate="active")

    def test_learn_timer(self):
        s = State(30)
        s.update(app_mode="learn")
        s.learn_deadline = 0
        self.assertEqual(s.learn_remain, 0)
        s.force_learn_off()
        self.assertEqual(s.app_mode, "normal")


if __name__ == "__main__":
    unittest.main()
