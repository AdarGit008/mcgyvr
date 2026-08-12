MOVES = {
    "created": {"pack": "packed"},
    "packed": {"ship": "shipped"},
    "shipped": {"deliver": "delivered", "bounce": "returned"},
}

KNOWN = frozenset({"pack", "ship", "deliver", "bounce"})


def trace_parcel(events):
    if not isinstance(events, list):
        raise ValueError("trace_parcel expects a list of events")
    state = "created"
    trail = [state]
    for event in events:
        if not isinstance(event, str) or event not in KNOWN:
            raise ValueError("unknown event: %r" % (event,))
        next_state = MOVES.get(state, {}).get(event)
        if next_state is None:
            raise ValueError("%s is not allowed in state %s" % (event, state))
        state = next_state
        trail.append(state)
    return trail
