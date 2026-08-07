def _whole(value, least: int, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < least:
        raise ValueError(f"{what} must be a whole number of at least {least}")
    return value


def resolve_dice_pool(pools: list, rolls: list) -> dict:
    """What each handful of dice is worth once the weakest are set aside."""
    if not isinstance(pools, list) or not pools:
        raise ValueError("there must be at least one pool")
    if not isinstance(rolls, list):
        raise ValueError("the rolls must be a list")

    totals = []
    dropped = []
    at = 0

    for pool in pools:
        sides = _whole(pool.get("sides"), 2, "sides")
        dice = _whole(pool.get("dice"), 1, "dice")
        keep = _whole(pool.get("keep"), 1, "keep")
        if keep > dice:
            raise ValueError(f"a pool cannot hold {keep} of {dice} dice")

        base = at
        taken = []
        for _ in range(dice):
            if at >= len(rolls):
                raise ValueError("the rolls run out")
            roll = rolls[at]
            at += 1
            if isinstance(roll, bool) or not isinstance(roll, int):
                raise ValueError(f"{roll} is not a roll of a {sides}-sided die")
            if roll < 1 or roll > sides:
                raise ValueError(f"{roll} is not a roll of a {sides}-sided die")
            taken.append(roll)

        order = sorted(range(len(taken)), key=lambda index: (-taken[index], index))
        held = set(order[:keep])

        total = 0
        aside = []
        for index in range(len(taken)):
            if index in held:
                total += taken[index]
            else:
                aside.append(base + index)
        totals.append(total)
        dropped.append(aside)

    if at != len(rolls):
        raise ValueError(f"{len(rolls) - at} rolls were left undrawn")
    return {"totals": totals, "dropped": dropped}
