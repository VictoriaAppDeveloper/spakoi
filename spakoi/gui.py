"""Native GTK/libadwaita interface for Spakoi."""

from __future__ import annotations

import json
import sys
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import config
from .daemon import BUS_NAME, INTERFACE, OBJECT_PATH
from .schedule import DAYS, Rule

DAY_LABELS = dict(zip(DAYS, ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")))


class TimePicker(Gtk.Box):
    def __init__(self, value: str) -> None:
        super().__init__(spacing=0, valign=Gtk.Align.CENTER, css_classes=["time-picker"])
        try:
            hour, minute = (int(part) for part in value.split(":"))
        except (AttributeError, ValueError):
            hour, minute = 0, 0
        hour = min(23, max(0, hour))
        minute = min(59, max(0, minute))
        self.hour = Gtk.DropDown(model=Gtk.StringList.new([f"{item:02d}" for item in range(24)]),
                                 selected=hour, enable_search=True,
                                 tooltip_text="Hours: 00 to 23")
        self.minute = Gtk.DropDown(model=Gtk.StringList.new([f"{item:02d}" for item in range(60)]),
                                   selected=minute, enable_search=True,
                                   tooltip_text="Minutes: 00 to 59")
        self.append(self.hour)
        self.append(Gtk.Label(label=":", css_classes=["time-separator"]))
        self.append(self.minute)

    def get_time(self) -> str:
        return f"{self.hour.get_selected():02d}:{self.minute.get_selected():02d}"


class RuleDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, rule: dict | None = None) -> None:
        super().__init__(title="Schedule interval", transient_for=parent, modal=True,
                         use_header_bar=True)
        self.add_css_class("spakoi-dialog")
        self._rule = rule
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Save", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(430, -1)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                          margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.get_content_area().append(content)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        content.append(grid)
        grid.attach(Gtk.Label(label="Name", xalign=0), 0, 0, 1, 1)
        self.identifier = Gtk.Entry(hexpand=True, placeholder_text="For example, quiet hours")
        self.identifier.set_text((rule or {}).get("id", ""))
        grid.attach(self.identifier, 1, 0, 3, 1)
        grid.attach(Gtk.Label(label="From", xalign=0), 0, 1, 1, 1)
        self.start = TimePicker((rule or {}).get("from", "09:00"))
        grid.attach(self.start, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="To", xalign=0), 2, 1, 1, 1)
        self.end = TimePicker((rule or {}).get("to", "17:00"))
        grid.attach(self.end, 3, 1, 1, 1)

        content.append(Gtk.Label(label="Days of the week", xalign=0, css_classes=["heading"]))
        days_box = Gtk.Box(spacing=6, homogeneous=True)
        content.append(days_box)
        selected = set((rule or {}).get("days", DAYS[:5]))
        self.days: dict[str, Gtk.ToggleButton] = {}
        for day in DAYS:
            button = Gtk.ToggleButton(label=DAY_LABELS[day], active=day in selected)
            days_box.append(button)
            self.days[day] = button

        protection = Gtk.Box(spacing=12, margin_top=4)
        protection_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        protection_text.append(Gtk.Label(label="Protect while active", xalign=0,
                                         css_classes=["heading"]))
        protection_text.append(Gtk.Label(
            label="While time is hidden, this interval cannot be stopped, edited, or deleted",
            xalign=0, wrap=True, css_classes=["dim-label"]))
        protection.append(protection_text)
        self.locked = Gtk.Switch(active=(rule or {}).get("locked", False),
                                 valign=Gtk.Align.CENTER,
                                 tooltip_text="A voluntary commitment that lasts until the interval ends")
        protection.append(self.locked)
        content.append(protection)

        self.error = Gtk.Label(xalign=0, wrap=True, css_classes=["error"])
        content.append(self.error)
        self.connect("response", self._validate_response)

    def _validate_response(self, dialog, response: int) -> None:
        if response != Gtk.ResponseType.OK:
            return
        try:
            Rule.from_dict(self.value())
        except (KeyError, ValueError) as exc:
            self.error.set_text(str(exc))
            dialog.stop_emission_by_name("response")

    def value(self) -> dict:
        return {
            "id": self.identifier.get_text().strip(),
            "enabled": (self._rule or {}).get("enabled", True),
            "locked": self.locked.get_active(),
            "days": [day for day, button in self.days.items() if button.get_active()],
            "from": self.start.get_time(),
            "to": self.end.get_time(),
        }


class Window(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application, title="Spakoi", default_width=620,
                         default_height=650)
        self.add_css_class("spakoi-window")
        self._data: dict = {}
        self._proxy: Gio.DBusProxy | None = None

        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(shell)
        header = Adw.HeaderBar()
        header.add_css_class("spakoi-header")
        brand = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        brand.append(Gtk.Image(icon_name="org.spakoi.Spakoi.UI", pixel_size=24))
        brand.append(Gtk.Label(label="Spakoi", css_classes=["title-2"]))
        header.set_title_widget(brand)
        shell.append(header)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        refresh.connect("clicked", lambda *_: self.refresh_status())
        header.pack_end(refresh)

        scrolled = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vexpand=True,
        )
        shell.append(scrolled)
        self.page_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.CROSSFADE,
            transition_duration=320,
            reveal_child=False,
        )
        scrolled.set_child(self.page_revealer)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22,
                       margin_top=24, margin_bottom=24, margin_start=24, margin_end=24,
                       css_classes=["spakoi-page"])
        self.page_revealer.set_child(page)
        GLib.idle_add(self._reveal_page)

        schedule_header = Gtk.Box(spacing=12)
        page.append(schedule_header)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        title_box.append(Gtk.Label(label="Schedule", xalign=0, css_classes=["title-2"]))
        title_box.append(Gtk.Label(label="Intervals when the clock is hidden", xalign=0,
                                   css_classes=["dim-label"]))
        schedule_header.append(title_box)
        self.add_button = Gtk.Button(label="＋ Add interval",
                                     tooltip_text="Choose days and time",
                                     valign=Gtk.Align.CENTER,
                                     css_classes=["suggested-action", "spakoi-add"])
        self.add_button.connect("clicked", lambda *_: self._edit_rule())
        schedule_header.append(self.add_button)

        self.rules_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                      css_classes=["boxed-list", "spakoi-list"])
        page.append(self.rules_list)
        self.message = Gtk.Label(xalign=0, wrap=True, css_classes=["error"])
        page.append(self.message)

        self._load_rules(animate=True)
        self._connect_service()

    def _reveal_page(self) -> bool:
        self.page_revealer.set_reveal_child(True)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _reveal_rule(revealer: Gtk.Revealer) -> bool:
        revealer.set_reveal_child(True)
        return GLib.SOURCE_REMOVE

    def _connect_service(self) -> None:
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
                BUS_NAME, OBJECT_PATH, INTERFACE, None)
            self._proxy.connect("g-signal", self._on_signal)
            self.refresh_status()
        except GLib.Error as exc:
            self._offline(exc.message)

    def _on_signal(self, _proxy, _sender, name: str, _parameters) -> None:
        if name == "StateChanged":
            self.refresh_status()

    def refresh_status(self) -> None:
        if not self._proxy:
            self._connect_service()
            return
        self._proxy.call("GetStatus", None, Gio.DBusCallFlags.NONE, 3000, None,
                         self._status_received)

    def _status_received(self, proxy, result) -> None:
        try:
            value = json.loads(proxy.call_finish(result).unpack()[0])
        except (GLib.Error, ValueError, KeyError) as exc:
            self._offline(str(exc))
            return
        self._data = value
        strict = value.get("mode") == "strict"
        self.add_button.set_sensitive(not strict)
        self.message.set_text("The schedule is protected by system policy" if strict else "")

    def _offline(self, details: str) -> None:
        self.message.set_text(f"Spakoi service is unavailable: {details}")

    def _call(self, method: str, parameters: GLib.Variant | None = None) -> None:
        if not self._proxy:
            self._connect_service()
            return
        self._proxy.call(method, parameters, Gio.DBusCallFlags.NONE, 3000, None,
                         lambda proxy, result: self._call_finished(proxy, result))

    def _call_finished(self, proxy, result) -> None:
        try:
            proxy.call_finish(result)
            self.message.set_text("")
            self.refresh_status()
        except GLib.Error as exc:
            self.message.set_text(exc.message)

    def _load_rules(self, animate: bool = False) -> None:
        while child := self.rules_list.get_first_child():
            self.rules_list.remove(child)
        try:
            data = config.load()
        except (OSError, ValueError) as exc:
            self.message.set_text(str(exc))
            return
        rules = data.get("rules", [])
        if not rules:
            row = Gtk.ListBoxRow(selectable=False)
            reveal = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                  transition_duration=240, reveal_child=not animate)
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                            margin_top=24, margin_bottom=24, margin_start=18, margin_end=18,
                            halign=Gtk.Align.CENTER)
            empty.append(Gtk.Label(label="Your schedule is empty", css_classes=["heading"]))
            empty.append(Gtk.Label(label="Add days of the week and a time interval",
                                   css_classes=["dim-label"]))
            create = Gtk.Button(label="＋ Add interval",
                                css_classes=["suggested-action", "spakoi-add"],
                                halign=Gtk.Align.CENTER)
            create.connect("clicked", lambda *_: self._edit_rule())
            empty.append(create)
            reveal.set_child(empty)
            row.set_child(reveal)
            self.rules_list.append(row)
            if animate:
                GLib.timeout_add(60, self._reveal_rule, reveal)
        for index, rule in enumerate(rules):
            enabled = rule.get("enabled", True)
            locked = rule.get("locked", False)
            protected = locked and enabled and bool(Rule.from_dict(rule, index).interval_containing(
                datetime.now().astimezone()))
            row = Gtk.ListBoxRow(selectable=False)
            reveal = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                  transition_duration=260, reveal_child=not animate)
            box = Gtk.Box(spacing=12, margin_top=10, margin_bottom=10,
                          margin_start=14, margin_end=10)
            reveal.set_child(box)
            row.set_child(reveal)
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            labels.append(Gtk.Label(label=rule.get("id", f"rule-{index + 1}"), xalign=0,
                                    css_classes=["heading"]))
            days = " ".join(DAY_LABELS.get(day, day) for day in rule["days"])
            labels.append(Gtk.Label(label=f"{days}   {rule['from']} — {rule['to']}", xalign=0,
                                    css_classes=["dim-label"]))
            labels.set_opacity(1.0 if enabled else 0.5)
            box.append(labels)
            if locked:
                box.append(Gtk.Image(icon_name="changes-prevent-symbolic",
                                     tooltip_text="Protection is active" if protected else "Protected interval"))
            toggle = Gtk.Button(
                icon_name="media-playback-pause-symbolic" if enabled else "media-playback-start-symbolic",
                tooltip_text="Stop interval" if enabled else "Start interval",
                valign=Gtk.Align.CENTER,
                css_classes=["spakoi-play" if not enabled else "spakoi-stop"],
            )
            toggle.set_sensitive(not protected)
            toggle.connect("clicked", lambda _button, i=index: self._toggle_rule(i))
            box.append(toggle)
            edit = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Edit",
                              valign=Gtk.Align.CENTER)
            edit.set_sensitive(not protected)
            edit.connect("clicked", lambda _button, i=index: self._edit_rule(i))
            box.append(edit)
            delete = Gtk.Button(icon_name="edit-delete-symbolic", tooltip_text="Delete",
                                valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
            delete.set_sensitive(not protected)
            delete.connect("clicked", lambda _button, i=index: self._delete_rule(i))
            box.append(delete)
            self.rules_list.append(row)
            if animate:
                GLib.timeout_add(45 * (index + 1), self._reveal_rule, reveal)

    def _toggle_rule(self, index: int) -> None:
        try:
            data = config.load()
            rule = data.setdefault("rules", [])[index]
            rule["enabled"] = not rule.get("enabled", True)
            config.write(data)
            self._call("Reload")
            self._load_rules()
        except (OSError, ValueError, IndexError) as exc:
            self.message.set_text(str(exc))

    def _edit_rule(self, index: int | None = None) -> None:
        data = config.load()
        current = data.get("rules", [])[index] if index is not None else None
        dialog = RuleDialog(self, current)
        dialog.connect("response", lambda item, response: self._save_dialog(item, response, index))
        dialog.present()

    def _save_dialog(self, dialog: RuleDialog, response: int, index: int | None) -> None:
        if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        value = dialog.value()
        try:
            data = config.load()
            rules = data.setdefault("rules", [])
            if index is None:
                rules.append(value)
            else:
                rules[index] = value
            config.write(data)
            self._call("Reload")
            self._load_rules()
            dialog.destroy()
        except (OSError, ValueError) as exc:
            dialog.error.set_text(str(exc))

    def _delete_rule(self, index: int) -> None:
        try:
            data = config.load()
            del data.setdefault("rules", [])[index]
            config.write(data)
            self._call("Reload")
            self._load_rules()
        except (OSError, ValueError, IndexError) as exc:
            self.message.set_text(str(exc))


class Application(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.spakoi.Spakoi.UI", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            window.spakoi-window,
            window.spakoi-window scrolledwindow,
            window.spakoi-window viewport {
                background: #17141d;
                color: #f6f5f4;
            }
            .spakoi-header {
                background: #211c29;
                color: #ffffff;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                box-shadow: 0 4px 14px rgba(0, 0, 0, 0.24);
            }
            .spakoi-header button {
                color: #ffffff;
                border-radius: 999px;
            }
            .spakoi-page {
                color: #f6f5f4;
            }
            .spakoi-page .title-2 {
                font-weight: 700;
                letter-spacing: -0.2px;
            }
            .spakoi-page .dim-label {
                color: #aaa2b3;
            }
            .spakoi-list {
                background: #282230;
                color: #f6f5f4;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
            }
            .spakoi-list row {
                background: transparent;
                color: #f6f5f4;
            }
            .spakoi-list row:first-child {
                border-radius: 16px 16px 0 0;
            }
            .spakoi-list row:last-child {
                border-radius: 0 0 16px 16px;
            }
            .spakoi-list row:not(:last-child) {
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            .spakoi-page button {
                border-radius: 10px;
                min-height: 28px;
                transition: 160ms ease-in-out;
            }
            button.spakoi-add {
                background-image: linear-gradient(to right, #3584e4, #9141ac);
                color: #ffffff;
                border-color: transparent;
                font-weight: 700;
                padding: 5px 16px;
                box-shadow: 0 4px 12px rgba(28, 113, 216, 0.28);
            }
            button.spakoi-add:hover {
                background-image: linear-gradient(to right, #62a0ea, #c061cb);
                box-shadow: 0 6px 16px rgba(145, 65, 172, 0.34);
            }
            button.spakoi-play {
                background: #2ec27e;
                color: #102a20;
                border-radius: 999px;
            }
            button.spakoi-stop {
                background: #43394f;
                color: #f6f5f4;
                border-radius: 999px;
            }
            window.spakoi-dialog {
                background: #282230;
                color: #f6f5f4;
            }
            window.spakoi-dialog headerbar {
                background: #211c29;
                color: #ffffff;
            }
            window.spakoi-dialog entry {
                border-radius: 10px;
            }
            .time-picker {
                background: #211c29;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 12px;
                padding: 2px;
                box-shadow: inset 0 1px rgba(255, 255, 255, 0.06);
            }
            .time-picker dropdown,
            .time-picker dropdown button {
                background: transparent;
                border: none;
                box-shadow: none;
                color: #ffffff;
                font-weight: 700;
                font-feature-settings: "tnum";
                border-radius: 9px;
                min-width: 52px;
            }
            .time-picker dropdown:hover {
                background: rgba(255, 255, 255, 0.08);
            }
            .time-picker .time-separator {
                color: #c061cb;
                font-weight: 800;
                font-size: 18px;
                padding: 0 2px;
            }
            window.spakoi-dialog button {
                border-radius: 9px;
            }
            window.spakoi-dialog switch:checked {
                background: #c061cb;
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self) -> None:
        window = self.props.active_window or Window(self)
        window.present()


def main() -> None:
    raise SystemExit(Application().run(sys.argv))


if __name__ == "__main__":
    main()
