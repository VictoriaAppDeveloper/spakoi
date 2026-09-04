import * as Main from 'resource:///org/gnome/shell/ui/main.js';

function actorsFromClock(clock) {
    if (!clock)
        return [];
    return [clock, clock._clock, clock._time, clock._date, clock._dateLabel, clock._timeLabel]
        .filter((actor, index, all) => actor && all.indexOf(actor) === index);
}

export function lockScreenActors() {
    const shield = Main.screenShield;
    const dialog = shield?._dialog ?? shield?._lockDialog ?? Main.sessionMode?._unlockDialog;
    return [
        ...actorsFromClock(dialog?._clock),
        ...actorsFromClock(dialog?._clockDisplay),
        ...actorsFromClock(shield?._clock),
    ].filter((actor, index, all) => actor && all.indexOf(actor) === index);
}
