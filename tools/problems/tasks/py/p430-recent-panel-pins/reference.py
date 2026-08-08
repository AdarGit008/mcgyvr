VERBS = ("open", "pin", "unpin", "forget")


def replay_recent_panel(limit: int, events: list[list[str]]) -> list[str]:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("the limit must be a whole number of at least 1")
    if not isinstance(events, list):
        raise ValueError("the events must be a list of pairs")

    pinned: list[str] = []
    recent: list[str] = []

    def trim() -> None:
        while len(recent) > limit:
            recent.pop()

    for event in events:
        if not isinstance(event, (list, tuple)) or len(event) != 2:
            raise ValueError("an event is a [verb, name] pair")
        verb, name = event
        if not isinstance(verb, str) or verb not in VERBS:
            raise ValueError("a verb is one of open, pin, unpin and forget")
        if not isinstance(name, str) or not name:
            raise ValueError("a name must be a non-empty string")

        held = name in pinned
        if verb == "open":
            if held:
                continue
            if name in recent:
                recent.remove(name)
            recent.insert(0, name)
            trim()
        elif verb == "pin":
            if held:
                continue
            if name in recent:
                recent.remove(name)
            pinned.append(name)
        elif verb == "unpin":
            if not held:
                continue
            pinned.remove(name)
            recent.insert(0, name)
            trim()
        else:
            if held:
                continue
            if name in recent:
                recent.remove(name)

    return pinned + recent
