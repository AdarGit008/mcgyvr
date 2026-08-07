def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def race_ladder_board(
    size: int, chutes: list[list[int]], turns: list[list]
) -> dict[str, int]:
    if not _whole(size) or size < 2:
        raise ValueError("size must be a whole number of at least 2")

    exit_of: dict[int, int] = {}
    for pair in chutes:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("a chute is a [mouth, exit] pair")
        mouth, landing = pair
        for square in (mouth, landing):
            if not _whole(square) or square < 1 or square > size:
                raise ValueError("a chute square must be a whole number on the lane")
        if mouth == landing:
            raise ValueError("a mouth may not be its own exit")
        if mouth == size:
            raise ValueError("the home square may not be a mouth")
        if mouth in exit_of:
            raise ValueError("two chutes share one mouth")
        exit_of[mouth] = landing
    for landing in exit_of.values():
        if landing in exit_of:
            raise ValueError("an exit may not be a mouth")

    standing: dict[str, int] = {}
    for turn in turns:
        if not isinstance(turn, (list, tuple)) or len(turn) != 2:
            raise ValueError("a turn is a [name, steps] pair")
        name, steps = turn
        if not isinstance(name, str) or not name:
            raise ValueError("a runner's name must be a non-empty string")
        if not _whole(steps) or steps < 1:
            raise ValueError("steps must be a whole number above zero")
        standing.setdefault(name, 0)
        start = standing[name]
        if start == size:
            continue
        arrival = start + steps
        if arrival > size:
            continue
        resting = exit_of.get(arrival, arrival)
        for other in standing:
            if other != name and standing[other] == resting:
                standing[other] = 0
        standing[name] = resting

    return dict(standing)
