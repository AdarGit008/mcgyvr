def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def ring_change_rows(bells: int, changes: list, count: int) -> list:
    if not _whole(bells) or bells < 2 or bells > 12:
        raise ValueError("the bells are not whole or fall outside two to twelve")
    if not isinstance(changes, list) or len(changes) == 0:
        raise ValueError("the changes are not a list or are empty")
    if not _whole(count) or count < 1:
        raise ValueError("the count is not whole or falls below one")

    standing = []
    for change in changes:
        if not isinstance(change, list):
            raise ValueError("a change is not a list")
        places = set()
        highest = 0
        for place in change:
            if not _whole(place) or place < 1 or place > bells:
                raise ValueError("a place is not whole or falls outside one to the bells")
            if place <= highest:
                raise ValueError("a change's places do not climb strictly")
            highest = place
            places.add(place)
        at = 1
        while at <= bells:
            if at in places:
                at += 1
                continue
            if at + 1 > bells or at + 1 in places:
                raise ValueError("a change's movers do not pair off")
            at += 2
        standing.append(places)

    row = list(range(1, bells + 1))
    rows = [row]
    for rung in range(1, count):
        places = standing[(rung - 1) % len(standing)]
        following = list(row)
        at = 1
        while at <= bells:
            if at in places:
                at += 1
                continue
            following[at - 1] = row[at]
            following[at] = row[at - 1]
            at += 2
        rows.append(following)
        row = following

    return rows
