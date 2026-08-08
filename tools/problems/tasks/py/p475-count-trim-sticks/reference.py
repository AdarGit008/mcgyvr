def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def count_trim_sticks(stick: int, calls: list, blade: int) -> dict:
    if not _whole(stick) or stick < 1:
        raise ValueError("the stick is not whole or falls below one")
    if not isinstance(calls, list):
        raise ValueError("the calls are not a list")
    if not _whole(blade) or blade < 0:
        raise ValueError("the blade is not whole or falls below nought")

    tails = []
    for call in calls:
        if not _whole(call) or call < 1:
            raise ValueError("a call is not whole or falls below one")
        if call > stick:
            raise ValueError("a call is longer than a fresh stick")
        if not tails or call > tails[-1]:
            tails.append(stick)
        rest = tails[-1] - call - blade
        tails[-1] = rest if rest > 0 else 0

    return {"sticks": len(tails), "tails": tails}
