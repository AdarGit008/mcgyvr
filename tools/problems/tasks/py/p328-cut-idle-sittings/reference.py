KINDS = ("hit", "reset")


def _text(value):
    return isinstance(value, str) and value != ""


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def cut_idle_sittings(events, gap, cap) -> list:
    if not isinstance(events, list):
        raise ValueError("the events must be a list")
    if not _whole(gap) or gap < 0:
        raise ValueError("gap must be a whole number of zero or more")
    if not _whole(cap) or cap < 0:
        raise ValueError("cap must be a whole number of zero or more")
    by_visitor = {}
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("an event must be a record")
        for name in ("who", "at", "kind"):
            if name not in event:
                raise ValueError("an event is missing " + name)
        if not _text(event["who"]):
            raise ValueError("who must be a non-empty string")
        if not _whole(event["at"]):
            raise ValueError("at must be a whole number")
        if event["kind"] not in KINDS:
            raise ValueError("kind must be hit or reset")
        by_visitor.setdefault(event["who"], []).append(
            (event["at"], event["kind"])
        )

    report = []
    for who in sorted(by_visitor):
        marks = sorted(by_visitor[who], key=lambda mark: mark[0])
        open_sitting = None
        previous = 0
        for at, kind in marks:
            fresh = (
                open_sitting is None
                or kind == "reset"
                or at - previous > gap
                or at - open_sitting["from"] > cap
            )
            if fresh:
                open_sitting = {"who": who, "from": at, "to": at, "count": 1}
                report.append(open_sitting)
            else:
                open_sitting["to"] = at
                open_sitting["count"] += 1
            previous = at
    return report
