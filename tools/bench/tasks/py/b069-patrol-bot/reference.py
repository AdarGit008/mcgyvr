def clamp_move(position, delta, width):
    if not isinstance(width, int) or width < 1:
        raise ValueError("width must be a positive integer")
    if not isinstance(position, int) or not 0 <= position < width:
        raise ValueError("position must sit inside the corridor")
    if not isinstance(delta, int) or delta == 0:
        raise ValueError("a move must be a non-zero integer")
    landed = min(width - 1, max(0, position + delta))
    return [landed, landed != position + delta]


def run_patrol(width, start, moves):
    if not isinstance(moves, list):
        raise ValueError("moves must be a list")
    seen = {start}
    position, bumps = start, 0
    for move in moves:
        position, bumped = clamp_move(position, move, width)
        seen.add(position)
        bumps += 1 if bumped else 0
    return {"position": position, "bumps": bumps, "visited": len(seen)}
