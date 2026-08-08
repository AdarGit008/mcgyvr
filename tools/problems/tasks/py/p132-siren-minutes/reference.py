def siren_minutes(events, horizon):
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    if not isinstance(horizon, int) or isinstance(horizon, bool):
        raise ValueError("horizon must be an integer")
    active = {}
    minutes = {}
    cursor = None

    def credit(up_to):
        if cursor is None:
            return
        span = up_to - cursor
        if span <= 0:
            return
        sounding = {}
        for ident, (channel, severity, raised_at) in active.items():
            best = sounding.get(channel)
            if (
                best is None
                or severity > best[1]
                or (severity == best[1] and raised_at < best[2])
            ):
                sounding[channel] = (ident, severity, raised_at)
        for ident, _severity, _raised_at in sounding.values():
            minutes[ident] = minutes.get(ident, 0) + span

    for event in events:
        if not isinstance(event, dict):
            raise ValueError("each event must be a record")
        at = event.get("at")
        kind = event.get("kind")
        ident = event.get("id")
        if not isinstance(at, int) or isinstance(at, bool):
            raise ValueError("at must be an integer")
        if cursor is not None and at <= cursor:
            raise ValueError("event times must strictly increase")
        if at > horizon:
            raise ValueError("an event past the horizon is malformed")
        if not isinstance(ident, str) or ident == "":
            raise ValueError("id must be a non-empty string")
        credit(at)
        cursor = at
        if kind == "raise":
            if ident in active:
                raise ValueError("raise of an id already active")
            channel = event.get("channel")
            severity = event.get("severity")
            if not isinstance(channel, str) or channel == "":
                raise ValueError("channel must be a non-empty string")
            if (
                not isinstance(severity, int)
                or isinstance(severity, bool)
                or severity < 1
                or severity > 5
            ):
                raise ValueError("severity must be an integer from 1 to 5")
            active[ident] = (channel, severity, cursor)
            minutes.setdefault(ident, 0)
        elif kind == "clear":
            if ident not in active:
                raise ValueError("clear of an id not active")
            del active[ident]
        else:
            raise ValueError("kind must be raise or clear")
    credit(horizon)
    return [[ident, total] for ident, total in sorted(minutes.items())]
