"""Configuration loading, validation and atomic persistence."""

from __future__ import annotations

import os
import json
import re
import tempfile
import tomllib
from datetime import datetime
from pathlib import Path

from .schedule import Rule

DEFAULT_CONFIG = """[general]
enabled = true
mode = "normal"

# [[rules]]
# id = "work-hours"
# enabled = true
# locked = false
# days = ["mon", "tue", "wed", "thu", "fri"]
# from = "09:00"
# to = "17:00"
"""


def user_config_path() -> Path:
    override = os.environ.get("SPAKOI_CONFIG") or os.environ.get("TIMEVEIL_CONFIG")
    if override:
        return Path(override)
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "spakoi/config.toml"


def config_path() -> Path:
    override = os.environ.get("SPAKOI_CONFIG") or os.environ.get("TIMEVEIL_CONFIG")
    if override:
        return Path(override)
    system = Path("/etc/spakoi/config.toml")
    legacy_system = Path("/etc/timeveil/config.toml")
    user = user_config_path()
    legacy_user = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "timeveil/config.toml"
    for candidate in (system, legacy_system):
        if not candidate.exists():
            continue
        try:
            with candidate.open("rb") as handle:
                if tomllib.load(handle).get("general", {}).get("mode") == "strict":
                    return candidate
        except (OSError, tomllib.TOMLDecodeError):
            return candidate
    if user.exists():
        return user
    if legacy_user.exists():
        return legacy_user
    if system.exists():
        return system
    if legacy_system.exists():
        return legacy_system
    return user


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    if not path.exists():
        return {"general": {"enabled": True, "mode": "normal"}, "rules": []}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    validate(data)
    return data


def strict_policy(path: Path | None = None) -> bool:
    """Conservatively detect strict mode, including in a malformed config."""
    path = path or config_path()
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle).get("general", {}).get("mode") == "strict"
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return False
        section = re.search(r"(?ms)^\s*\[general\]\s*$\n(.*?)(?=^\s*\[|\Z)", text)
        return bool(section and re.search(
            r"(?m)^\s*mode\s*=\s*['\"]strict['\"]\s*(?:#.*)?$", section.group(1)))


def validate(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("configuration root must be a table")
    general = data.get("general", {})
    if not isinstance(general, dict):
        raise ValueError("general must be a table")
    if not isinstance(general.get("enabled", True), bool):
        raise ValueError("general.enabled must be a boolean")
    if general.get("mode", "normal") not in {"normal", "strict"}:
        raise ValueError("general.mode must be 'normal' or 'strict'")
    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("rules must be an array of tables")
    ids: set[str] = set()
    for index, raw in enumerate(raw_rules):
        if not isinstance(raw, dict):
            raise ValueError(f"rule {index + 1} must be a table")
        if not isinstance(raw.get("enabled", True), bool):
            raise ValueError(f"rule {index + 1} enabled must be a boolean")
        if not isinstance(raw.get("locked", False), bool):
            raise ValueError(f"rule {index + 1} locked must be a boolean")
        rule = Rule.from_dict(raw, index)
        if rule.id in ids:
            raise ValueError(f"duplicate rule id: {rule.id}")
        ids.add(rule.id)


def rules(data: dict) -> list[Rule]:
    return [Rule.from_dict(raw, index) for index, raw in enumerate(data.get("rules", []))
            if raw.get("enabled", True)]


def locked_rule_ids(data: dict, now: datetime | None = None) -> set[str]:
    now = now or datetime.now().astimezone()
    result = set()
    for index, raw in enumerate(data.get("rules", [])):
        rule = Rule.from_dict(raw, index)
        if raw.get("enabled", True) and raw.get("locked", False) and rule.interval_containing(now):
            result.add(rule.id)
    return result


def ensure_locked_rules_unchanged(previous: dict, updated: dict,
                                  now: datetime | None = None) -> None:
    protected = locked_rule_ids(previous, now)
    if not protected:
        return
    old = {Rule.from_dict(raw, index).id: raw
           for index, raw in enumerate(previous.get("rules", []))}
    new = {Rule.from_dict(raw, index).id: raw
           for index, raw in enumerate(updated.get("rules", []))}
    disabled_globally = (previous.get("general", {}).get("enabled", True) and
                         not updated.get("general", {}).get("enabled", True))
    changed = [identifier for identifier in protected
               if disabled_globally or new.get(identifier) != old[identifier]]
    if changed:
        raise PermissionError(
            "protected interval cannot be edited, stopped, or deleted while time is hidden: "
            + ", ".join(sorted(changed)))


def write(data: dict, path: Path | None = None) -> None:
    validate(data)
    selected_before_write = path or config_path()
    if selected_before_write.exists():
        ensure_locked_rules_unchanged(load(selected_before_write), data)
    if path is None:
        selected = config_path()
        is_strict = data.get("general", {}).get("mode") == "strict"
        system_paths = {Path("/etc/spakoi/config.toml"), Path("/etc/timeveil/config.toml")}
        path = selected if selected not in system_paths or is_strict else user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = dump(data)
    fd, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def dump(data: dict) -> str:
    general = data.get("general", {})
    lines = ["[general]", f'enabled = {str(general.get("enabled", True)).lower()}',
             f'mode = {json.dumps(general.get("mode", "normal"), ensure_ascii=False)}', ""]
    for index, raw in enumerate(data.get("rules", [])):
        rule = Rule.from_dict(raw, index)
        day_values = ", ".join(f'"{day}"' for day in rule.days)
        lines += ["[[rules]]", f'id = {json.dumps(rule.id, ensure_ascii=False)}',
                  f'enabled = {str(raw.get("enabled", True)).lower()}', f"days = [{day_values}]",
                  f'locked = {str(raw.get("locked", False)).lower()}',
                  f'from = "{rule.start:%H:%M}"', f'to = "{rule.end:%H:%M}"', ""]
    return "\n".join(lines)
