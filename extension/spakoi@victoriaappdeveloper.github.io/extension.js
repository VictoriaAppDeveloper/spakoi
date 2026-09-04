import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {Controller} from './src/controller.js';

export default class SpakoiExtension extends Extension {
    enable() {
        this._controller = new Controller(this.path);
        this._controller.enable();
    }

    disable() {
        this._controller?.disable();
        this._controller = null;
    }
}
