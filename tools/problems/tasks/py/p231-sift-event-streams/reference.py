RANK = ["chatter", "notice", "alarm", "panic"]


def sift_event_streams(lanes: list, events: list) -> dict:
    if not isinstance(lanes, list):
        raise ValueError("the lanes must be a list")
    if not isinstance(events, list):
        raise ValueError("the events must be a list")
    names = []
    prefixes = []
    ceilings = []
    finals = []
    order = []
    took = {}
    for lane in lanes:
        if not isinstance(lane, dict):
            raise ValueError("a lane must be a mapping")
        name = lane.get("name")
        prefix = lane.get("prefix")
        up_to = lane.get("upTo")
        last = lane.get("last")
        if not isinstance(name, str) or not name:
            raise ValueError("a name must be a non-empty string")
        if not isinstance(prefix, str):
            raise ValueError("a prefix must be a string")
        if not isinstance(up_to, str) or up_to not in RANK:
            raise ValueError("a severity must be one of the four words")
        if not isinstance(last, bool):
            raise ValueError("last is either true or false")
        if name not in took:
            took[name] = []
            order.append(name)
        names.append(name)
        prefixes.append(prefix)
        ceilings.append(RANK.index(up_to))
        finals.append(last)
    dropped = []
    for at, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError("an event must be a mapping")
        channel = event.get("channel")
        severity = event.get("severity")
        if not isinstance(channel, str) or not channel:
            raise ValueError("a channel must be a non-empty string")
        if not isinstance(severity, str) or severity not in RANK:
            raise ValueError("a severity must be one of the four words")
        rank = RANK.index(severity)
        caught = False
        for which, name in enumerate(names):
            if not channel.startswith(prefixes[which]):
                continue
            if rank > ceilings[which]:
                continue
            held = took[name]
            if not held or held[-1] != at:
                held.append(at)
            caught = True
            if finals[which]:
                break
        if not caught:
            dropped.append(at)
    return {
        "lanes": [{"name": name, "took": took[name]} for name in order],
        "dropped": dropped,
    }
