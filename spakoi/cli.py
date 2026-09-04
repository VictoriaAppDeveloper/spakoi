"""Command-line interface for Spakoi."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timedelta

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import config
from .daemon import BUS_NAME, INTERFACE, OBJECT_PATH
from .schedule import DAYS


def proxy() -> Gio.DBusProxy:
    return Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
                                           BUS_NAME, OBJECT_PATH, INTERFACE, None)


def call(method: str, signature: str | None = None, values: tuple = ()):
    parameters = GLib.Variant(signature, values) if signature else None
    return proxy().call_sync(method, parameters, Gio.DBusCallFlags.NONE, 3000, None)


def duration(value: str) -> int:
    match = re.fullmatch(r"(\d+)([smhd])", value.lower())
    if not match:
        raise argparse.ArgumentTypeError("duration must look like 30m, 2h, or 1d")
    return int(match.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]


def parse_days(value: str) -> list[str]:
    result: list[str] = []
    for part in value.lower().split(","):
        if "-" in part:
            start, end = part.split("-", 1)
            if start not in DAYS or end not in DAYS:
                raise argparse.ArgumentTypeError("days must use mon..sun")
            indexes = list(range(DAYS.index(start), DAYS.index(end) + 1))
            if not indexes:
                raise argparse.ArgumentTypeError("invalid day range")
            result.extend(DAYS[index] for index in indexes)
        elif part in DAYS:
            result.append(part)
        else:
            raise argparse.ArgumentTypeError("days must use mon..sun")
    return list(dict.fromkeys(result))


def until_seconds(value: str) -> int:
    try:
        hour, minute = map(int, value.split(":"))
        target = datetime.now().astimezone().replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("time must be HH:MM") from exc
    if target <= datetime.now().astimezone():
        target += timedelta(days=1)
    return max(1, int((target - datetime.now().astimezone()).total_seconds()))


def status() -> None:
    raw = call("GetStatus").unpack()[0]
    value = json.loads(raw)
    print(f"State: {value['state']}")
    print(f"Reason: {value['reason']}")
    if value.get("rule_id"):
        print(f"Active rule: {value['rule_id']}")
    if value.get("next_transition"):
        print(f"Next transition: {value['next_transition']}")
    print(f"Mode: {value['mode']}")


def notify_reload() -> None:
    try:
        call("Reload")
    except GLib.Error:
        pass


def schedule_command(args) -> None:
    data = config.load()
    items = data.setdefault("rules", [])
    if args.schedule_action == "list":
        if not items:
            print("No schedule rules.")
        for index, rule in enumerate(items):
            state = "enabled" if rule.get("enabled", True) else "stopped"
            protection = ", protected" if rule.get("locked", False) else ""
            print(f"{rule.get('id', f'rule-{index + 1}')}: {','.join(rule['days'])} "
                  f"{rule['from']}-{rule['to']} [{state}{protection}]")
        return
    if data.get("general", {}).get("mode") == "strict":
        raise PermissionError("operation denied in strict mode; administrator privileges are required")
    if args.schedule_action == "add":
        identifier = args.id or f"rule-{len(items) + 1}"
        if any(item.get("id") == identifier for item in items):
            raise ValueError(f"rule already exists: {identifier}")
        items.append({"id": identifier, "enabled": True, "locked": False, "days": args.days,
                      "from": args.start, "to": args.end})
    elif args.schedule_action == "remove":
        remaining = [item for index, item in enumerate(items) if item.get("id", f"rule-{index + 1}") != args.id]
        if len(remaining) == len(items):
            raise ValueError(f"unknown rule: {args.id}")
        data["rules"] = remaining
    elif args.schedule_action == "clear":
        data["rules"] = []
    config.write(data)
    notify_reload()


def doctor() -> int:
    checks = []
    checks.append(("Configuration", _check_config()))
    checks.append(("D-Bus service", proxy().get_name_owner() is not None))
    extension = "/usr/share/gnome-shell/extensions/spakoi@victoriaappdeveloper.github.io/metadata.json"
    checks.append(("System extension", __import__("pathlib").Path(extension).exists()))
    checks.append(("GNOME Shell tools", shutil.which("gnome-extensions") is not None))
    for name, ok in checks:
        print(f"{'OK' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in checks) else 1


def _check_config() -> bool:
    try:
        config.validate(config.load())
        return True
    except Exception:
        return False


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="spakoi")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    for name in ("hide", "show"):
        command = commands.add_parser(name)
        group = command.add_mutually_exclusive_group()
        group.add_argument("--for", dest="for_seconds", type=duration)
        group.add_argument("--until", type=until_seconds)
    commands.add_parser("enable")
    commands.add_parser("disable")
    commands.add_parser("doctor")
    configuration = commands.add_parser("config")
    configuration.add_subparsers(dest="config_action", required=True).add_parser("validate")
    schedule = commands.add_parser("schedule").add_subparsers(dest="schedule_action", required=True)
    schedule.add_parser("list")
    add = schedule.add_parser("add")
    add.add_argument("--id")
    add.add_argument("--days", required=True, type=parse_days)
    add.add_argument("--from", dest="start", required=True)
    add.add_argument("--to", dest="end", required=True)
    remove = schedule.add_parser("remove")
    remove.add_argument("id")
    schedule.add_parser("clear")
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "status":
            status()
        elif args.command in {"hide", "show"}:
            seconds = args.for_seconds or args.until
            method = args.command.title() + ("For" if seconds else "")
            call(method, "(u)", (seconds,)) if seconds else call(method)
        elif args.command in {"enable", "disable"}:
            data = config.load()
            if data.get("general", {}).get("mode") == "strict":
                raise PermissionError("operation denied in strict mode; administrator privileges are required")
            data.setdefault("general", {})["enabled"] = args.command == "enable"
            config.write(data)
            notify_reload()
        elif args.command == "schedule":
            schedule_command(args)
        elif args.command == "config":
            config.validate(config.load())
            print(f"Configuration is valid: {config.config_path()}")
        elif args.command == "doctor":
            raise SystemExit(doctor())
    except (GLib.Error, OSError, ValueError, PermissionError) as exc:
        print(f"spakoi: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
