def _call_cycle(order: str, count: int) -> list:
    up = list(range(count))
    if order == "round":
        return up
    if order == "reverse":
        return up[::-1]
    return up + up[::-1]


def deal_packet(items: list, seats: list, order: str) -> dict:
    if not isinstance(items, list):
        raise ValueError("the packet must be a list")
    seen = set()
    for item in items:
        if not isinstance(item, str) or item == "":
            raise ValueError("every packet entry must be a non-empty string")
        if item in seen:
            raise ValueError("the packet repeats " + item)
        seen.add(item)
    if not isinstance(seats, list) or len(seats) == 0:
        raise ValueError("the limits must be a non-empty list")
    for limit in seats:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("every limit must be a whole number above zero")
    if order not in ("round", "reverse", "snake"):
        raise ValueError("unknown turn sequence: " + str(order))

    cycle = _call_cycle(order, len(seats))
    hands = [[] for _ in seats]
    left = []
    room = sum(seats)
    at = 0
    for item in items:
        if room == 0:
            left.append(item)
            continue
        while len(hands[cycle[at % len(cycle)]]) >= seats[cycle[at % len(cycle)]]:
            at += 1
        hands[cycle[at % len(cycle)]].append(item)
        at += 1
        room -= 1
    return {"hands": hands, "left": left}
