import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from spakoi.schedule import Rule, evaluate


TZ = ZoneInfo("Europe/Warsaw")


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=TZ)


class ScheduleTests(unittest.TestCase):
    def test_regular_interval_boundaries(self):
        rule = Rule.from_dict({"id": "work", "days": ["thu"], "from": "09:00", "to": "17:00"})
        self.assertFalse(evaluate([rule], at("2026-09-03T08:59")).hidden)
        self.assertTrue(evaluate([rule], at("2026-09-03T09:00")).hidden)
        self.assertTrue(evaluate([rule], at("2026-09-03T16:59")).hidden)
        self.assertFalse(evaluate([rule], at("2026-09-03T17:00")).hidden)

    def test_overnight_uses_start_day(self):
        rule = Rule.from_dict({"id": "night", "days": ["thu"], "from": "22:00", "to": "07:00"})
        self.assertFalse(evaluate([rule], at("2026-09-03T21:59")).hidden)
        self.assertTrue(evaluate([rule], at("2026-09-03T22:00")).hidden)
        self.assertTrue(evaluate([rule], at("2026-09-04T02:00")).hidden)
        self.assertFalse(evaluate([rule], at("2026-09-04T07:00")).hidden)

    def test_overlap_does_not_create_false_transition(self):
        first = Rule.from_dict({"days": ["thu"], "from": "09:00", "to": "12:00"}, 0)
        second = Rule.from_dict({"days": ["thu"], "from": "11:00", "to": "14:00"}, 1)
        result = evaluate([first, second], at("2026-09-03T10:00"))
        self.assertEqual(result.next_transition, at("2026-09-03T14:00"))

    def test_next_start(self):
        rule = Rule.from_dict({"days": ["thu"], "from": "09:00", "to": "17:00"})
        self.assertEqual(evaluate([rule], at("2026-09-03T08:00")).next_transition,
                         at("2026-09-03T09:00"))

    def test_dst_timezone_is_retained(self):
        rule = Rule.from_dict({"days": ["sun"], "from": "01:00", "to": "04:00"})
        result = evaluate([rule], at("2026-03-29T03:30"))
        self.assertTrue(result.hidden)
        self.assertEqual(result.next_transition.hour, 4)


if __name__ == "__main__":
    unittest.main()

