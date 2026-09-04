import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Config from 'resource:///org/gnome/shell/misc/config.js';

import {StateClient} from './dbus.js';
import {Indicator} from './indicator.js';
import {lockScreenActors as actors49} from './compat/gnome49.js';
import {lockScreenActors as actors50} from './compat/gnome50.js';

export class Controller {
    constructor(extensionPath) {
        this._extensionPath = extensionPath;
        this._hidden = false;
        this._strictDeployment = this._readStrictPolicy();
        this._original = new Map();
        this._actorSignals = new Map();
        this._signals = [];
        this._idleIds = new Set();
        this._retryId = 0;
        this._enabled = false;
    }

    _readStrictPolicy() {
        for (const path of ['/etc/spakoi/config.toml', '/etc/timeveil/config.toml']) {
            try {
                const [ok, bytes] = Gio.File.new_for_path(path).load_contents(null);
                if (ok && this._strictFromText(new TextDecoder().decode(bytes)))
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
        this._enabled = true;
        this._indicator = new Indicator(this._extensionPath);
        Main.panel.addToStatusArea('spakoi', this._indicator);
        this._connectClient();
        this._signals.push([Main.sessionMode, Main.sessionMode.connect('updated', () => this._apply())]);
        this._signals.push([Main.screenShield, Main.screenShield.connect('active-changed', () => {
            const id = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                this._idleIds.delete(id);
                if (this._enabled)
                    this._apply();
                return GLib.SOURCE_REMOVE;
            });
            this._idleIds.add(id);
        })]);
    }

    _connectClient() {
        this._client?.destroy();
        this._client = new StateClient(
            state => {
                this._hidden = state === 'HIDDEN' ||
                    (this._strictDeployment && state !== 'VISIBLE');
                this._indicator?.setState(state);
                this._apply();
            },
            () => {
                // Strict deployments fail closed; normal mode retains the last state.
                if (this._strictDeployment) {
                    this._hidden = true;
                    this._apply();
                }
                if (!this._retryId)
                    this._retryId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 30, () => {
                        this._retryId = 0;
                        this._connectClient();
                        return GLib.SOURCE_REMOVE;
                    });
            });
    }

    _actors() {
        const dateMenu = Main.panel?.statusArea?.dateMenu;
        const major = Number.parseInt(Config.PACKAGE_VERSION.split('.')[0]);
        const lockActors = major >= 50 ? actors50() : actors49();
        return [dateMenu?.container ?? dateMenu, ...lockActors].filter(Boolean);
    }

    _apply() {
        for (const actor of this._actors()) {
            if (!this._original.has(actor)) {
                this._original.set(actor, actor.visible);
                const id = actor.connect('destroy', destroyed => {
                    this._original.delete(destroyed);
                    this._actorSignals.delete(destroyed);
                });
                this._actorSignals.set(actor, id);
            }
            actor.visible = this._hidden ? false : this._original.get(actor);
        }
    }

    disable() {
        this._enabled = false;
        this._indicator?.destroy();
        this._indicator = null;
        this._client?.destroy();
        this._client = null;
        if (this._retryId)
            GLib.source_remove(this._retryId);
        this._retryId = 0;
        for (const id of this._idleIds)
            GLib.source_remove(id);
        this._idleIds.clear();
        for (const [object, id] of this._signals)
            object.disconnect(id);
        this._signals = [];
        for (const [actor, visible] of this._original) {
            if (!actor.is_destroyed?.())
                actor.visible = visible;
        }
        for (const [actor, id] of this._actorSignals) {
            if (!actor.is_destroyed?.())
                actor.disconnect(id);
        }
        this._actorSignals.clear();
        this._original.clear();
    }
}
