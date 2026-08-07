import re

SHAPE = re.compile(r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*")


def _groups(name, raw):
    if not isinstance(raw, str) or SHAPE.fullmatch(raw) is None:
        raise ValueError("a release is not written in the stated shape: " + str(name))
    return [int(part) for part in raw.split(".")]


def _rank(left, right):
    reach = max(len(left), len(right))
    for at in range(reach):
        here = left[at] if at < len(left) else 0
        there = right[at] if at < len(right) else 0
        if here != there:
            return -1 if here < there else 1
    return 0


def _read(book):
    if not isinstance(book, dict):
        raise ValueError("a lock record is not a mapping")
    held = {}
    for name, raw in book.items():
        if not isinstance(name, str) or not name:
            raise ValueError("a package name is not a non-empty string")
        held[name] = _groups(name, raw)
    return held


def summarise_lock_diff(before: dict, after: dict) -> dict:
    was = _read(before)
    now = _read(after)
    added = []
    dropped = []
    lifted = []
    lowered = []

    for name in sorted(set(was) | set(now)):
        if name not in was:
            added.append(name)
            continue
        if name not in now:
            dropped.append(name)
            continue
        verdict = _rank(was[name], now[name])
        if verdict < 0:
            lifted.append(name)
        elif verdict > 0:
            lowered.append(name)
    return {
        "added": added,
        "dropped": dropped,
        "lifted": lifted,
        "lowered": lowered,
    }
