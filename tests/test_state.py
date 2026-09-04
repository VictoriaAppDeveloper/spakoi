import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from spakoi.state import Override, effective, load_override
from spakoi.daemon import schedule_reset_allowed


class StateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 3, 10, tzinfo=timezone.utc)
        self.config = {"general": {"enabled": True, "mode": "normal"}, "rules": [{
            "id": "work", "days": ["thu"], "from": "09:00", "to": "17:00"
        }]}

    def test_schedule(self):
        result = effective(self.config, None, self.now)
        self.assertEqual((result["state"], result["reason"]), ("HIDDEN", "schedule"))

    def test_temporary_show_wins(self):
        override = Override(False, (self.now + timedelta(minutes=10)).isoformat())
        result = effective(self.config, override, self.now)
        self.assertEqual((result["state"], result["reason"]), ("VISIBLE", "temporary-override"))

    def test_expired_override_returns_to_schedule(self):
        override = Override(False, (self.now - timedelta(seconds=1)).isoformat())
        self.assertEqual(effective(self.config, override, self.now)["reason"], "schedule")

    def test_disabled_defaults_visible(self):
        self.config["general"]["enabled"] = False
        self.assertEqual(effective(self.config, None, self.now)["state"], "VISIBLE")

    def test_stopped_rule_is_ignored(self):
        self.config["rules"][0]["enabled"] = False
        result = effective(self.config, None, self.now)
        self.assertEqual((result["state"], result["reason"]), ("VISIBLE", "default"))

    def test_protected_schedule_wins_over_show_override(self):
        self.config["rules"][0]["locked"] = True
        override = Override(False, (self.now + timedelta(minutes=10)).isoformat())
        result = effective(self.config, override, self.now)
        self.assertEqual((result["state"], result["reason"]),
                         ("HIDDEN", "protected-schedule"))

    def test_invalid_override_types_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps({"hidden": "false"}), encoding="utf-8")
            self.assertIsNone(load_override(path))

    def test_naive_override_timestamp_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps({"hidden": False, "until": "2026-09-04T12:00:00"}),
                            encoding="utf-8")
            self.assertIsNone(load_override(path))

    def test_strict_mode_cannot_reset_to_visible_schedule(self):
        strict = {"general": {"enabled": True, "mode": "strict"}, "rules": []}
        self.assertFalse(schedule_reset_allowed(
            strict, {"state": "HIDDEN"}, self.now))

    def test_strict_mode_can_reset_during_hidden_schedule(self):
        self.config["general"]["mode"] = "strict"
        self.assertTrue(schedule_reset_allowed(
            self.config, {"state": "HIDDEN"}, self.now))

    def test_normal_mode_keeps_schedule_reset_behavior(self):
        self.assertTrue(schedule_reset_allowed(
            self.config, {"state": "HIDDEN"}, self.now))


if __name__ == "__main__":
    unittest.main()
