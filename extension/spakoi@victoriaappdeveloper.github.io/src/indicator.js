import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Util from 'resource:///org/gnome/shell/misc/util.js';

export const Indicator = GObject.registerClass(
class Indicator extends PanelMenu.Button {
    constructor(extensionPath) {
        super(0.0, 'Spakoi');
        const iconPath = `${extensionPath}/icons/spakoi-panel.svg`;
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
