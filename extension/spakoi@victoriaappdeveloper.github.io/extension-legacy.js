/* GNOME Shell 43 compatibility entry point (pre-ES-module extension API). */
const {Gio, GLib, GObject} = imports.gi;
const Main = imports.ui.main;
const UnlockDialog = imports.ui.unlockDialog;
const PanelMenu = imports.ui.panelMenu;
const PopupMenu = imports.ui.popupMenu;
const St = imports.gi.St;
const Util = imports.misc.util;
const ExtensionUtils = imports.misc.extensionUtils;

const BUS_NAME = 'org.spakoi.Spakoi';
const OBJECT_PATH = '/org/spakoi/Spakoi';
const XML = `<node><interface name="org.spakoi.Spakoi">
  <method name="GetStatus"><arg name="status" type="s" direction="out"/></method>
  <method name="HideFor"><arg name="seconds" type="u" direction="in"/></method>
  <method name="Show"/>
  <signal name="StateChanged"><arg name="state" type="s"/><arg name="reason" type="s"/></signal>
</interface></node>`;
const Proxy = Gio.DBusProxy.makeProxyWrapper(XML);

const Indicator = GObject.registerClass(
class Indicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'Spakoi');
        const iconPath = `${ExtensionUtils.getCurrentExtension().path}/icons/spakoi-panel.svg`;
        this.add_child(new St.Icon({
            gicon: Gio.icon_new_for_string(iconPath),
            style_class: 'system-status-icon spakoi-panel-icon',
        }));
        this._stateItem = new PopupMenu.PopupMenuItem('Spakoi: connecting…', {reactive: false});
        this.menu.addMenuItem(this._stateItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const open = new PopupMenu.PopupMenuItem('Open Spakoi');
        open.connect('activate', () => Util.spawn(['spakoi-gui']));
        this.menu.addMenuItem(open);
    }

    setState(state) {
        this._stateItem.label.text = state === 'HIDDEN'
            ? 'Spakoi: time is hidden'
            : 'Spakoi: time is visible';
    }
});

class Extension {
    constructor() {
        this._hidden = false;
        this._original = new Map();
        this._signals = [];
        this._clockSignals = new Map();
        this._retryId = 0;
        this._strict = this._readStrictPolicy();
    }

    _readStrictPolicy() {
        for (const path of ['/etc/spakoi/config.toml', '/etc/timeveil/config.toml']) {
            try {
                const [ok, bytes] = GLib.file_get_contents(path);
                if (ok && this._strictFromText(imports.byteArray.toString(bytes)))
                    return true;
            } catch (_error) {
                // Try the legacy location when the new configuration is absent.
            }
        }
        return false;
    }

    _strictFromText(text) {
        const section = text.match(/^\s*\[general\]\s*$\r?\n([\s\S]*?)(?=^\s*\[|(?![\s\S]))/m);
        return Boolean(section && /^\s*mode\s*=\s*["']strict["']\s*(?:#.*)?$/m.test(section[1]));
    }

    enable() {
        this._patchClockCreation();
        this._connectClient();
        this._signals.push([Main.sessionMode,
            Main.sessionMode.connect('updated', () => this._apply())]);
        this._signals.push([Main.screenShield,
            Main.screenShield.connect('active-changed', () => {
                // GNOME 43 creates _dialog lazily while locking the screen.
                GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                    this._apply();
                    return GLib.SOURCE_REMOVE;
                });
            })]);
    }

    _patchClockCreation() {
        if (!UnlockDialog.Clock || this._originalClockInit)
            return;
        const controller = this;
        this._originalClockInit = UnlockDialog.Clock.prototype._init;
        UnlockDialog.Clock.prototype._init = function (...args) {
            controller._originalClockInit.apply(this, args);
            // Store the pre-Spakoi state before hiding at creation time.
            controller._original.set(this, this.visible);
            const signal = this.connect('notify::visible', actor => {
                if (controller._hidden && actor.visible)
                    actor.hide();
            });
            controller._clockSignals.set(this, signal);
            this.connect('destroy', actor => controller._clockSignals.delete(actor));
            if (controller._hidden)
                this.hide();
        };
    }

    _connectClient() {
        if (this._proxy && this._signal)
            this._proxy.disconnectSignal(this._signal);
        this._proxy = new Proxy(Gio.DBus.session, BUS_NAME, OBJECT_PATH,
            (proxy, error) => {
                if (error) {
                    this._unavailable();
                    return;
                }
                this._signal = proxy.connectSignal('StateChanged',
                    (_proxy, _sender, [state]) => {
                        if (state === 'HIDDEN' || state === 'VISIBLE')
                            this._setState(state);
                        else
                            this._unavailable();
                    });
                this._indicator = new Indicator();
                Main.panel.addToStatusArea('spakoi', this._indicator);
                proxy.GetStatusRemote((result, callError) => {
                    if (callError)
                        this._unavailable();
                    else {
                        try {
                            const state = JSON.parse(result[0]).state;
                            if (state !== 'HIDDEN' && state !== 'VISIBLE')
                                throw new Error('Invalid Spakoi state');
                            this._setState(state);
                        } catch (_error) {
                            this._unavailable();
                        }
                    }
                });
            });
    }

    _setState(state) {
        this._hidden = state === 'HIDDEN' || (this._strict && state !== 'VISIBLE');
        if (this._indicator)
            this._indicator.setState(state);
        this._apply();
    }

    _unavailable() {
        if (this._strict) {
            this._hidden = true;
            this._apply();
        }
        if (!this._retryId)
            this._retryId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 30, () => {
                this._retryId = 0;
                this._connectClient();
                return GLib.SOURCE_REMOVE;
            });
    }

    _actors() {
        const dateMenu = Main.panel && Main.panel.statusArea.dateMenu;
        const shield = Main.screenShield;
        const dialog = shield && (shield._dialog || shield._lockDialog);
        const clocks = [dialog && dialog._clock, dialog && dialog._clockDisplay,
            shield && shield._clock].filter(Boolean);
        const actors = [dateMenu && (dateMenu.container || dateMenu)];
        for (const clock of clocks)
            actors.push(clock, clock._clock, clock._time, clock._date,
                clock._dateLabel, clock._timeLabel);
        return actors.filter((actor, index, all) => actor && all.indexOf(actor) === index);
    }

    _apply() {
        for (const actor of this._actors()) {
            if (!this._original.has(actor))
                this._original.set(actor, actor.visible);
            actor.visible = this._hidden ? false : this._original.get(actor);
        }
    }

    disable() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
        if (this._originalClockInit) {
            UnlockDialog.Clock.prototype._init = this._originalClockInit;
            this._originalClockInit = null;
        }
        for (const [clock, id] of this._clockSignals) {
            try {
                clock.disconnect(id);
            } catch (error) {
                // The clock can be destroyed as the session mode changes.
            }
        }
        this._clockSignals.clear();
        if (this._proxy && this._signal)
            this._proxy.disconnectSignal(this._signal);
        this._proxy = null;
        this._signal = 0;
        if (this._retryId)
            GLib.source_remove(this._retryId);
        this._retryId = 0;
        for (const [object, id] of this._signals)
            object.disconnect(id);
        this._signals = [];
        for (const [actor, visible] of this._original) {
            try {
                actor.visible = visible;
            } catch (error) {
                // Actor may have been destroyed during a session-mode change.
            }
        }
        this._original.clear();
    }
}

function init() {
    return new Extension();
}
