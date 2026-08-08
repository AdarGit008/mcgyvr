def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def trace_arrears_steps(opening: int, due_day: int, events: list) -> list:
    if not _whole(opening) or opening < 1:
        raise ValueError("the opening sum is not whole or falls below one")
    if not _whole(due_day) or due_day < 0:
        raise ValueError("the due day is not whole or falls below nought")
    if not isinstance(events, list):
        raise ValueError("trace_arrears_steps expects a list of events")

    labels = []
    owing = opening
    anchor = due_day
    clock = 0
    started = False

    for event in events:
        if not isinstance(event, dict):
            raise ValueError("an event is not a mapping")
        kind = event.get("kind")
        if kind not in ("pay", "check"):
            raise ValueError("an event's kind is outside pay and check")
        wanted = ["cents", "day", "kind"] if kind == "pay" else ["day", "kind"]
        if sorted(event) != wanted:
            raise ValueError("an event's keys are not the ones its kind calls for")
        day = event["day"]
        if not _whole(day) or day < 0:
            raise ValueError("a day is not whole or falls below nought")
        if started and day < clock:
            raise ValueError("a day steps backwards")
        clock = day
        started = True

        if kind == "pay":
            cents = event["cents"]
            if not _whole(cents) or cents < 1:
                raise ValueError("a payment is not whole or falls below one")
            owing = max(0, owing - cents)
            if owing > 0:
                anchor = clock
            continue

        if owing == 0:
            labels.append("settled")
            continue
        age = clock - anchor
        if age <= 0:
            labels.append("current")
        elif age <= 9:
            labels.append("reminder")
        elif age <= 24:
            labels.append("warning")
        elif age <= 44:
            labels.append("demand")
        else:
            labels.append("referred")
    return labels
