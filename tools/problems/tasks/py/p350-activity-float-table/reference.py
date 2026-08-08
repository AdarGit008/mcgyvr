from collections import deque


def activity_float_table(activities: list[dict]) -> list[str]:
    if not isinstance(activities, list) or len(activities) == 0:
        raise ValueError("the plan must be a non-empty list")
    days: dict[str, int] = {}
    waits: dict[str, list[str]] = {}
    for entry in activities:
        if not isinstance(entry, dict):
            raise ValueError("every entry must be a mapping")
        name = entry.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("a name must be a non-empty string")
        if name in days:
            raise ValueError("two entries share a name")
        span = entry.get("days")
        if isinstance(span, bool) or not isinstance(span, int) or span <= 0:
            raise ValueError("days must be a whole number above zero")
        after = entry.get("after")
        if not isinstance(after, list):
            raise ValueError("the after list must be a list")
        for earlier in after:
            if not isinstance(earlier, str):
                raise ValueError("the after list must hold strings")
            if earlier == name:
                raise ValueError("an activity may not wait on itself")
        days[name] = span
        waits[name] = list(after)
    for after in waits.values():
        for earlier in after:
            if earlier not in days:
                raise ValueError("an after entry names no activity in the plan")

    names = sorted(days)
    followers: dict[str, list[str]] = {name: [] for name in names}
    pending: dict[str, int] = {}
    for name in names:
        pending[name] = len(waits[name])
        for earlier in waits[name]:
            followers[earlier].append(name)
    order: list[str] = []
    ready = deque(name for name in names if pending[name] == 0)
    while ready:
        name = ready.popleft()
        order.append(name)
        for later in followers[name]:
            pending[later] -= 1
            if pending[later] == 0:
                ready.append(later)
    if len(order) != len(names):
        raise ValueError("the waiting forms a loop")

    start: dict[str, int] = {}
    finish: dict[str, int] = {}
    for name in order:
        earliest = 0
        for earlier in waits[name]:
            earliest = max(earliest, finish[earlier])
        start[name] = earliest
        finish[name] = earliest + days[name]
    span = max(finish[name] for name in names)

    late_start: dict[str, int] = {}
    for name in reversed(order):
        latest_finish = span
        for later in followers[name]:
            latest_finish = min(latest_finish, late_start[later])
        late_start[name] = latest_finish - days[name]

    return [
        f"{name} {start[name]} {late_start[name]} {late_start[name] - start[name]}"
        for name in names
    ]
