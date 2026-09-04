"""Spakoi session service (Gio D-Bus implementation)."""

from __future__ import annotations

import json
import logging
import signal
from datetime import datetime, timedelta

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import config
from .state import Override, effective, load_override, save_override, state_path

BUS_NAME = "org.spakoi.Spakoi"
OBJECT_PATH = "/org/spakoi/Spakoi"
INTERFACE = BUS_NAME

INTROSPECTION = """
<node><interface name="org.spakoi.Spakoi">
  <method name="Hide"/><method name="Show"/>
  <method name="HideFor"><arg name="seconds" type="u" direction="in"/></method>
  <method name="ShowFor"><arg name="seconds" type="u" direction="in"/></method>
  <method name="UseSchedule"/>
  <method name="Reload"/>
  <method name="GetStatus"><arg name="status" type="s" direction="out"/></method>
  <property name="State" type="s" access="read"/>
  <property name="Reason" type="s" access="read"/>
  <property name="NextTransition" type="s" access="read"/>
  <property name="Mode" type="s" access="read"/>
  <signal name="StateChanged"><arg name="state" type="s"/><arg name="reason" type="s"/></signal>
</interface></node>
"""


def schedule_reset_allowed(data: dict, current: dict, now: datetime) -> bool:
    """Return whether clearing a manual override preserves strict-mode hiding."""
    if data.get("general", {}).get("mode") != "strict":
        return True
    if current.get("state") != "HIDDEN":
        return True
    return effective(data, None, now).get("state") == "HIDDEN"


class Service:
    def __init__(self) -> None:
        self.connection: Gio.DBusConnection | None = None
        self.timer = 0
        self.current: dict = {}
        self.node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)
        self.monitor = None
        self.system_bus = None
        self.strict = False

    def now(self) -> datetime:
        return datetime.now().astimezone()

    def start(self, connection: Gio.DBusConnection) -> None:
        self.connection = connection
        connection.register_object(OBJECT_PATH, self.node.interfaces[0], self.on_method, self.on_property)
        path = config.config_path()
        self.strict = config.strict_policy(path)
        if self.strict:
            self.current = self._failure_state()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            config.write({"general": {"enabled": True, "mode": "normal"}, "rules": []}, path)
        self.monitor = Gio.File.new_for_path(str(path)).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", lambda *_: self.recompute())
        self._watch_system_changes()
        self.recompute()

    def _watch_system_changes(self) -> None:
        """Re-evaluate immediately after resume and timezone/time changes."""
        try:
            self.system_bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            self.system_bus.signal_subscribe(
                "org.freedesktop.login1", "org.freedesktop.login1.Manager", "PrepareForSleep",
                "/org/freedesktop/login1", None, Gio.DBusSignalFlags.NONE,
                lambda _bus, _sender, _path, _interface, _signal, params: self.recompute()
                if not params.unpack()[0] else None)
            self.system_bus.signal_subscribe(
                "org.freedesktop.timedate1", "org.freedesktop.DBus.Properties", "PropertiesChanged",
                "/org/freedesktop/timedate1", None, Gio.DBusSignalFlags.NONE,
                lambda *_: self.recompute())
        except GLib.Error:
            logging.warning("System bus unavailable; using five-minute fallback checks")

    def recompute(self) -> None:
        try:
            now = self.now()
            override = load_override()
            if override and override.until and datetime.fromisoformat(override.until) <= now:
                save_override(None)
                override = None
            updated = effective(config.load(), override, now)
        except Exception:
            logging.exception("Could not calculate state; retaining last state")
            self.strict = config.strict_policy()
            if self.strict:
                self._publish(self._failure_state())
            self.schedule_timer()
            return
        self.strict = updated.get("mode") == "strict"
        self._publish(updated)
        self.schedule_timer()

    def _failure_state(self) -> dict:
        now = self.now().isoformat()
        return {"hidden": True, "state": "HIDDEN", "reason": "strict-error",
                "rule_id": None, "since": now, "next_transition": None, "mode": "strict"}

    def _publish(self, updated: dict) -> None:
        changed = (updated.get("state"), updated.get("reason")) != (self.current.get("state"), self.current.get("reason"))
        self.current = updated
        if changed and self.connection:
            logging.info("State changed to %s (%s)", updated["state"], updated["reason"])
            self.connection.emit_signal(None, OBJECT_PATH, INTERFACE, "StateChanged",
                                        GLib.Variant("(ss)", (updated["state"], updated["reason"])))
            changed_properties = {key: GLib.Variant("s", str(updated.get(source) or "")) for key, source in
                                  (("State", "state"), ("Reason", "reason"),
                                   ("NextTransition", "next_transition"), ("Mode", "mode"))}
            self.connection.emit_signal(None, OBJECT_PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                                        GLib.Variant("(sa{sv}as)", (INTERFACE, changed_properties, [])))

    def schedule_timer(self) -> None:
        if self.timer:
            GLib.source_remove(self.timer)
        delay = 300
        if self.current.get("next_transition"):
            transition = datetime.fromisoformat(self.current["next_transition"])
            delay = max(1, min(delay, int((transition - self.now()).total_seconds()) + 1))
        self.timer = GLib.timeout_add_seconds(delay, self._timer_fired)

    def _timer_fired(self) -> bool:
        self.timer = 0
        self.recompute()
        return GLib.SOURCE_REMOVE

    def _set_override(self, hidden: bool, seconds: int | None = None) -> None:
        current_config = config.load()
        if not hidden and config.locked_rule_ids(current_config, self.now()):
            raise PermissionError(
                "operation denied: protected interval is active until scheduled end")
        if not hidden and current_config.get("general", {}).get("mode") == "strict":
            raise PermissionError("operation denied in strict mode; administrator privileges are required")
        until = (self.now() + timedelta(seconds=seconds)).isoformat() if seconds else None
        save_override(Override(hidden, until))
        self.recompute()

    def on_method(self, _connection, _sender, _path, _interface, method, parameters, invocation) -> None:
        try:
            if method == "Hide":
                self._set_override(True)
            elif method == "Show":
                self._set_override(False)
            elif method in {"HideFor", "ShowFor"}:
                self._set_override(method == "HideFor", parameters.unpack()[0])
            elif method == "UseSchedule":
                current_config = config.load()
                if not schedule_reset_allowed(current_config, self.current, self.now()):
                    raise PermissionError(
                        "operation denied: strict mode cannot reveal hidden time")
                save_override(None)
                self.recompute()
            elif method == "Reload":
                self.recompute()
            elif method == "GetStatus":
                invocation.return_value(GLib.Variant("(s)", (json.dumps(self.current),)))
                return
            else:
                invocation.return_dbus_error(
                    "org.spakoi.Spakoi.Error.UnknownMethod", f"unknown method: {method}")
                return
            invocation.return_value(None)
        except PermissionError as exc:
            invocation.return_dbus_error("org.spakoi.Spakoi.Error.Denied", str(exc))
        except Exception as exc:
            logging.exception("D-Bus request failed")
            invocation.return_dbus_error("org.spakoi.Spakoi.Error.Failed", str(exc))

    def on_property(self, _connection, _sender, _path, _interface, prop):
        mapping = {"State": "state", "Reason": "reason", "NextTransition": "next_transition", "Mode": "mode"}
        return GLib.Variant("s", str(self.current.get(mapping[prop]) or ""))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    loop = GLib.MainLoop()
    service = Service()

    def acquired(connection, _name):
        service.start(connection)

    def lost(_connection, _name):
        logging.error("Could not acquire or retain %s", BUS_NAME)
        loop.quit()

    Gio.bus_own_name(Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.DO_NOT_QUEUE, acquired, None,
                     lost)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (loop.quit(), False)[1])
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: (loop.quit(), False)[1])
    loop.run()


if __name__ == "__main__":
    main()
