def move_stock(opening: int, moves: list) -> int:
    held = opening
    for move in moves:
        held += move
        if held < 0:
            held = 0
    return held
