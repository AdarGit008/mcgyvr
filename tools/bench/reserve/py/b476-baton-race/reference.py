def baton_race(legs: list[int], handover: int) -> int:
    if len(legs) == 0:
        return 0
    total = 0
    for leg in legs:
        total += leg
    return total + handover * (len(legs) - 1)
