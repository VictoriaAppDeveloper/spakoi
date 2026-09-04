"""Timezone-aware weekly schedule evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Iterable

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def parse_clock(value: str) -> time:
    try:
        hour, minute = (int(part) for part in value.split(":"))
        return time(hour, minute)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid time {value!r}; expected HH:MM") from exc


@dataclass(frozen=True)
class Rule:
    id: str
    days: tuple[str, ...]
    start: time
    end: time

    @classmethod
    def from_dict(cls, raw: dict, index: int = 0) -> "Rule":
        if not isinstance(raw, dict):
            raise ValueError(f"rule {index + 1} must be a table")
        days = tuple(str(day).lower() for day in raw.get("days", ()))
        unknown = set(days) - set(DAYS)
        if not days or unknown:
            raise ValueError(f"rule days are invalid: {sorted(unknown) or days}")
        return cls(
            id=str(raw.get("id") or f"rule-{index + 1}"),
            days=days,
            start=parse_clock(raw["from"]),
            end=parse_clock(raw["to"]),
        )

    def interval_containing(self, now: datetime) -> tuple[datetime, datetime] | None:
        """Return the local interval containing now, including overnight tails."""
        for offset in (0, -1):
            day = now.date() + timedelta(days=offset)
            if DAYS[day.weekday()] not in self.days:
                continue
            start = datetime.combine(day, self.start, tzinfo=now.tzinfo)
            end_day = day + timedelta(days=1) if self.end <= self.start else day
            end = datetime.combine(end_day, self.end, tzinfo=now.tzinfo)
            if start <= now < end:
                return start, end
        return None

    def boundaries(self, now: datetime, horizon_days: int = 8) -> Iterable[datetime]:
        base = now.date() - timedelta(days=1)
        for offset in range(horizon_days + 2):
            day = base + timedelta(days=offset)
            if DAYS[day.weekday()] not in self.days:
                continue
            start = datetime.combine(day, self.start, tzinfo=now.tzinfo)
            end_day = day + timedelta(days=1) if self.end <= self.start else day
            yield start
            yield datetime.combine(end_day, self.end, tzinfo=now.tzinfo)


@dataclass(frozen=True)
class ScheduleResult:
    hidden: bool
    rule_id: str | None
    since: datetime | None
    next_transition: datetime | None


def evaluate(rules: Iterable[Rule], now: datetime) -> ScheduleResult:
    rules = tuple(rules)
    active = [(rule, interval) for rule in rules if (interval := rule.interval_containing(now))]
    hidden = bool(active)
    rule_id = active[0][0].id if active else None
    since = min((interval[0] for _, interval in active), default=None)

    boundaries = sorted({point for rule in rules for point in rule.boundaries(now) if point > now})
    next_transition = None
    for point in boundaries:
        probe = point + timedelta(microseconds=1)
        if bool(any(rule.interval_containing(probe) for rule in rules)) != hidden:
            next_transition = point
            break
    return ScheduleResult(hidden, rule_id, since, next_transition)
