def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _advance(col, row, move):
    odd = row % 2 == 1
    if move == "e":
        return col + 1, row
    if move == "w":
        return col - 1, row
    if move == "ne":
        return (col + 1 if odd else col), row - 1
    if move == "nw":
        return (col if odd else col - 1), row - 1
    if move == "se":
        return (col + 1 if odd else col), row + 1
    if move == "sw":
        return (col if odd else col - 1), row + 1
    raise ValueError("unrecognised move name")


def hop_offset_grid(start, moves):
    if not isinstance(start, list) or len(start) != 2:
        raise ValueError("the start must be a two-element address")
    if not _whole(start[0]) or not _whole(start[1]):
        raise ValueError("an address must hold whole numbers")
    if not isinstance(moves, list):
        raise ValueError("the moves must be a list")
    col, row = start[0], start[1]
    for move in moves:
        col, row = _advance(col, row, move)
    from_q = start[0] - (start[1] // 2)
    to_q = col - (row // 2)
    dq = to_q - from_q
    dr = row - start[1]
    distance = (abs(dq) + abs(dr) + abs(dq + dr)) // 2
    return {"cell": [col, row], "distance": distance}
