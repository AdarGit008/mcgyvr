TRANSITIONS = {
    "queued": {"start": "printing", "cancel": "cancelled"},
    "printing": {
        "pause": "paused",
        "jam": "blocked",
        "finish": "done",
        "cancel": "cancelled",
    },
    "paused": {"resume": "printing", "cancel": "cancelled"},
    "blocked": {"clear": "printing", "cancel": "cancelled"},
    "done": {},
    "cancelled": {},
}

EVENT_NAMES = frozenset(
    ["start", "pause", "resume", "jam", "clear", "finish", "cancel"]
)


def trace_print_job(events, pause_limit):
    if isinstance(pause_limit, bool) or not isinstance(pause_limit, int):
        raise ValueError("pause cap must be a non-negative integer")
    if pause_limit < 0:
        raise ValueError("pause cap must be a non-negative integer")
    state = "queued"
    pauses = 0
    jams = 0
    path = ["queued"]
    for event in events:
        if not isinstance(event, str) or event not in EVENT_NAMES:
            raise ValueError(f"unknown event: {event!r}")
        nxt = TRANSITIONS[state].get(event)
        if nxt is None:
            raise ValueError(f"event {event} does not apply in state {state}")
        if event == "pause":
            if pauses == pause_limit:
                raise ValueError("pause cap exhausted")
            pauses += 1
        if event == "jam":
            jams += 1
        state = nxt
        path.append(state)
    return {"state": state, "pauses": pauses, "jams": jams, "path": path}
