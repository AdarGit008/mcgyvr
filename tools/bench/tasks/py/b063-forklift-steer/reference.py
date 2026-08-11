"""Steer a forklift across a warehouse floor of aisles by bays."""

STEPS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}


def steer_forklift(aisles: int, bays: int, moves: list) -> list:
    for size in (aisles, bays):
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError("floor sizes must be positive integers")
    x = 0
    y = 0
    for move in moves:
        if move not in STEPS:
            raise ValueError("unknown move: " + move)
        dx, dy = STEPS[move]
        x += dx
        y += dy
        if x < 0 or x >= aisles or y < 0 or y >= bays:
            raise ValueError("the forklift would leave the floor")
    return [x, y]
