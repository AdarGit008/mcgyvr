import re

SHAPE = re.compile(
    r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*(\+[0-9a-z]+(\.[0-9a-z]+)*)?"
)


def _read(record):
    if not isinstance(record, list):
        raise ValueError("a lock record is not a list")
    held = {}
    for row in record:
        if not isinstance(row, dict):
            raise ValueError("an entry is not a mapping")
        if sorted(row) != ["name", "needs", "source", "version"]:
            raise ValueError("an entry carries exactly name, version, source and needs")
        name = row["name"]
        if not isinstance(name, str) or not name:
            raise ValueError("an entry's name is not a non-empty string")
        if name in held:
            raise ValueError("two entries of one record share a name")
        version = row["version"]
        if not isinstance(version, str) or SHAPE.fullmatch(version) is None:
            raise ValueError("a version is not written in the stated shape")
        source = row["source"]
        if not isinstance(source, str) or not source:
            raise ValueError("an entry's source is not a non-empty string")
        needs = row["needs"]
        if not isinstance(needs, list):
            raise ValueError("an entry's needs are not a list")
        wants = []
        for want in needs:
            if not isinstance(want, str) or not want:
                raise ValueError("a need is not a non-empty string")
            if want in wants:
                raise ValueError("an entry names one need twice")
            wants.append(want)
        digits = version.split("+")[0]
        held[name] = {
            "version": version,
            "groups": [int(part) for part in digits.split(".")],
            "source": source,
            "needs": wants,
        }
    return held


def _rank(left, right):
    reach = max(len(left), len(right))
    for at in range(reach):
        here = left[at] if at < len(left) else 0
        there = right[at] if at < len(right) else 0
        if here != there:
            return -1 if here < there else 1
    return 0


def report_lock_changes(before: list, after: list) -> dict:
    was = _read(before)
    now = _read(after)
    added = []
    dropped = []
    lifted = []
    lowered = []
    rebuilt = []
    moved = []
    rewired = []

    for name in sorted(set(was) | set(now)):
        if name not in was:
            added.append({"name": name, "version": now[name]["version"]})
            continue
        if name not in now:
            dropped.append({"name": name, "version": was[name]["version"]})
            continue
        old = was[name]
        fresh = now[name]
        verdict = _rank(old["groups"], fresh["groups"])
        if verdict < 0:
            lifted.append(
                {"name": name, "from": old["version"], "to": fresh["version"]}
            )
            continue
        if verdict > 0:
            lowered.append(
                {"name": name, "from": old["version"], "to": fresh["version"]}
            )
            continue
        if old["version"] != fresh["version"]:
            rebuilt.append(
                {"name": name, "from": old["version"], "to": fresh["version"]}
            )
        if old["source"] != fresh["source"]:
            moved.append({"name": name, "from": old["source"], "to": fresh["source"]})
        gained = sorted(set(fresh["needs"]) - set(old["needs"]))
        lost = sorted(set(old["needs"]) - set(fresh["needs"]))
        if gained or lost:
            rewired.append({"name": name, "gained": gained, "lost": lost})

    return {
        "added": added,
        "dropped": dropped,
        "lifted": lifted,
        "lowered": lowered,
        "rebuilt": rebuilt,
        "moved": moved,
        "rewired": rewired,
    }
