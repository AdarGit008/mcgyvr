"""A small room rota: overlap test, room assignment, and peak occupancy."""


def _check_span(span, label):
    start, end = span
    for endpoint in (start, end):
        if isinstance(endpoint, bool) or not isinstance(endpoint, int):
            raise ValueError(f"{label} endpoints must be integers")
    if start >= end:
        raise ValueError(f"{label} start must precede its end")


def spans_overlap(a: list, b: list) -> bool:
    _check_span(a, "span")
    _check_span(b, "span")
    return a[0] < b[1] and b[0] < a[1]


def assign_rooms(meetings: list) -> list:
    for meeting in meetings:
        _check_span(meeting, "meeting")
    order = sorted(
        range(len(meetings)),
        key=lambda i: (meetings[i][0], meetings[i][1], i),
    )
    last_in_room = []
    rooms = [0] * len(meetings)
    for position in order:
        meeting = meetings[position]
        assigned = -1
        for room, last in enumerate(last_in_room):
            if not spans_overlap(last, meeting):
                assigned = room
                break
        if assigned == -1:
            assigned = len(last_in_room)
            last_in_room.append(meeting)
        else:
            last_in_room[assigned] = meeting
        rooms[position] = assigned
    return rooms


def peak_rooms(meetings: list) -> int:
    rooms = assign_rooms(meetings)
    return max((room + 1 for room in rooms), default=0)
