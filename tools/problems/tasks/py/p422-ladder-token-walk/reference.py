def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def walk_ladder_board(size: int, chutes: list[list[int]], pushes: list[int]) -> int:
    if not _whole(size) or size < 2:
        raise ValueError("size must be a whole number of at least 2")
    if not isinstance(chutes, list) or not isinstance(pushes, list):
        raise ValueError("chutes and pushes must be lists")

    exit_of: dict[int, int] = {}
    for pair in chutes:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("a chute is a [mouth, exit] pair")
        mouth, landing = pair
        for square in (mouth, landing):
            if not _whole(square) or square < 1 or square > size:
                raise ValueError("a chute square must be a whole number on the track")
        if mouth == landing:
            raise ValueError("a mouth may not be its own exit")
        if mouth == 1 or mouth == size:
            raise ValueError("a mouth may not sit on the first or last square")
        if mouth in exit_of:
            raise ValueError("two chutes share one mouth")
        exit_of[mouth] = landing
    for landing in exit_of.values():
        if landing in exit_of:
            raise ValueError("an exit may not be a mouth")
    for push in pushes:
        if not _whole(push) or push < 1:
            raise ValueError("a push must be a whole number above zero")

    at = 1
    for push in pushes:
        if at == size:
            break
        landing = at + push
        if landing > size:
            continue
        at = exit_of.get(landing, landing)
    return at
