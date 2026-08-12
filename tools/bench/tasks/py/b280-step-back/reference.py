def step_back(moves: str) -> int:
    here = 0
    furthest = 0
    for move in moves:
        if move == "F":
            here += 1
        elif move == "B":
            here -= 1
        if here > furthest:
            furthest = here
    return furthest
