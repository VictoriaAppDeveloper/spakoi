import tempfile
import unittest
from pathlib import Path

from spakoi import config


class ConfigTests(unittest.TestCase):
    def test_round_trip(self):
        data = {"general": {"enabled": True, "mode": "normal"}, "rules": [{
            "id": "night", "enabled": True, "locked": False, "days": ["fri", "sat"],
            "from": "22:00", "to": "07:00"
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            config.write(data, path)
            self.assertEqual(config.load(path), data)

    def test_rejects_duplicate_ids(self):
        rule = {"id": "same", "days": ["mon"], "from": "09:00", "to": "10:00"}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            config.validate({"rules": [rule, rule]})

    def test_rule_id_is_safely_serialized(self):
        data = {"general": {"enabled": True, "mode": "normal"}, "rules": [{
            "id": 'quiet "hours"\nweekend', "enabled": True, "locked": False,
            "days": ["sat"], "from": "09:00", "to": "10:00"
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            config.write(data, path)
            self.assertEqual(config.load(path), data)

    def test_rejects_non_boolean_security_fields(self):
        with self.assertRaisesRegex(ValueError, "boolean"):
            config.validate({"general": {"enabled": "false", "mode": "normal"}})

    def test_detects_strict_policy_in_malformed_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[general]\nmode = "strict"\nbroken = [\n', encoding="utf-8")
            self.assertTrue(config.strict_policy(path))

    def test_does_not_treat_comment_as_strict_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[general]\n# mode = "strict"\nbroken = [\n', encoding="utf-8")
            self.assertFalse(config.strict_policy(path))

    def test_active_locked_rule_cannot_change(self):
        from datetime import datetime, timezone

        old = {"rules": [{"id": "focus", "enabled": True, "locked": True,
                           "days": ["thu"], "from": "09:00", "to": "17:00"}]}
        new = {"rules": [{**old["rules"][0], "enabled": False}]}
        now = datetime(2026, 9, 3, 12, tzinfo=timezone.utc)
        with self.assertRaisesRegex(PermissionError, "cannot be edited"):
            config.ensure_locked_rules_unchanged(old, new, now)

    def test_inactive_locked_rule_can_change(self):
        from datetime import datetime, timezone

        old = {"rules": [{"id": "focus", "enabled": True, "locked": True,
                           "days": ["thu"], "from": "09:00", "to": "17:00"}]}
        new = {"rules": [{**old["rules"][0], "enabled": False}]}
        now = datetime(2026, 9, 3, 18, tzinfo=timezone.utc)
        config.ensure_locked_rules_unchanged(old, new, now)

    def test_active_locked_rule_blocks_global_disable(self):
        from datetime import datetime, timezone

        rule = {"id": "focus", "enabled": True, "locked": True,
                "days": ["thu"], "from": "09:00", "to": "17:00"}
        old = {"general": {"enabled": True}, "rules": [rule]}
        new = {"general": {"enabled": False}, "rules": [rule]}
        now = datetime(2026, 9, 3, 12, tzinfo=timezone.utc)
        with self.assertRaises(PermissionError):
            config.ensure_locked_rules_unchanged(old, new, now)


if __name__ == "__main__":
    unittest.main()
