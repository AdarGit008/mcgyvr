def day_next(today: int, wanted: int) -> int:
    gap = wanted - today
    if gap <= 0:
        gap += 7
    return gap
