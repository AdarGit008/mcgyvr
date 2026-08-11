def live_count(neighbours: list) -> int:
    living = 0
    for neighbour in neighbours:
        if neighbour:
            living += 1
    return living


def live_next(alive: bool, neighbours: list) -> bool:
    living = live_count(neighbours)
    if alive:
        return living in (2, 3)
    return living == 3
