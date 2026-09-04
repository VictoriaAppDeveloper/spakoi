import Gio from 'gi://Gio';

const XML = `<node><interface name="org.spakoi.Spakoi">
  <method name="GetStatus"><arg name="status" type="s" direction="out"/></method>
  <property name="State" type="s" access="read"/>
  <property name="Mode" type="s" access="read"/>
  <signal name="StateChanged"><arg name="state" type="s"/><arg name="reason" type="s"/></signal>
</interface></node>`;

const Proxy = Gio.DBusProxy.makeProxyWrapper(XML);

function validState(state) {
    return state === 'HIDDEN' || state === 'VISIBLE';
}

export class StateClient {
    constructor(onState, onUnavailable) {
        this._proxy = new Proxy(
            Gio.DBus.session,
            'org.spakoi.Spakoi',
            '/org/spakoi/Spakoi',
            (proxy, error) => {
                if (error) {
                    onUnavailable();
                    return;
                }
                this._signal = proxy.connectSignal('StateChanged', (_proxy, _sender, [state]) => {
                    if (validState(state))
                        onState(state);
                    else
                        onUnavailable();
                });
                proxy.GetStatusRemote((result, callError) => {
                    if (callError) {
                        onUnavailable();
                        return;
                    }
                    try {
                        const state = JSON.parse(result[0]).state;
                        if (!validState(state))
                            throw new Error('Invalid Spakoi state');
                        onState(state);
                    } catch (_error) {
                        onUnavailable();
                    }
                });
            });
    }

    destroy() {
        if (this._signal)
            this._proxy.disconnectSignal(this._signal);
        this._proxy = null;
    }
}
