"""Persistent overrides and deterministic effective-state calculation."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .config import locked_rule_ids, rules
from .schedule import evaluate


def state_path() -> Path:
    override = os.environ.get("SPAKOI_STATE") or os.environ.get("TIMEVEIL_STATE")
    if override:
        return Path(override)
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "spakoi/state.json"


@dataclass
class Override:
    hidden: bool
    until: str | None = None


def load_override(path: Path | None = None) -> Override | None:
    path = path or state_path()
    if not path.exists() and not (os.environ.get("SPAKOI_STATE") or os.environ.get("TIMEVEIL_STATE")):
        legacy = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "timeveil/state.json"
        if legacy.exists():
            path = legacy
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "hidden" not in raw:
            return None
        if not isinstance(raw["hidden"], bool):
            return None
        until = raw.get("until")
        if until is not None:
            if not isinstance(until, str):
                return None
            parsed = datetime.fromisoformat(until)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return None
        return Override(raw["hidden"], until)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_override(override: Override | None, path: Path | None = None) -> None:
    path = path or state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {} if override is None else asdict(override)
    fd, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def effective(config: dict, override: Override | None, now: datetime) -> dict:
    mode = config.get("general", {}).get("mode", "normal")
    enabled = config.get("general", {}).get("enabled", True)
    if override and override.until and datetime.fromisoformat(override.until) <= now:
        override = None
    schedule = evaluate(rules(config), now)
    protected = locked_rule_ids(config, now) if enabled else set()
    if protected:
        hidden, reason, next_transition = True, "protected-schedule", schedule.next_transition
    elif override is not None:
        hidden, reason = override.hidden, "temporary-override" if override.until else "manual"
        next_transition = datetime.fromisoformat(override.until) if override.until else None
    elif enabled and schedule.hidden:
        hidden, reason, next_transition = True, "schedule", schedule.next_transition
    else:
        hidden, reason, next_transition = False, "default", schedule.next_transition if enabled else None
    return {
        "hidden": hidden,
        "state": "HIDDEN" if hidden else "VISIBLE",
        "reason": reason,
        "rule_id": schedule.rule_id if reason == "schedule" else None,
        "since": schedule.since.isoformat() if reason == "schedule" and schedule.since else now.isoformat(),
        "next_transition": next_transition.isoformat() if next_transition else None,
        "mode": mode,
    }
