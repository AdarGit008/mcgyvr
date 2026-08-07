STEPS = (
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
    (-2, -2),
    (-2, 2),
    (2, -2),
    (2, 2),
)


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def count_piece_tours(
    width: int, height: int, start: list[int], blocked: list[list[int]]
) -> int:
    if not _whole(width) or width < 1:
        raise ValueError("width must be an integer of at least 1")
    if not _whole(height) or height < 1:
        raise ValueError("height must be an integer of at least 1")

    def on_board(square: object) -> bool:
        return (
            isinstance(square, list)
            and len(square) == 2
            and _whole(square[0])
            and _whole(square[1])
            and 0 <= square[0] < height
            and 0 <= square[1] < width
        )

    if not isinstance(blocked, list):
        raise ValueError("blocked must be a list")
    shut: set[int] = set()
    for square in blocked:
        if not on_board(square):
            raise ValueError("a blocked square must be a pair naming a board square")
        key = square[0] * width + square[1]
        if key in shut:
            raise ValueError("blocked names the same square twice")
        shut.add(key)
    open_squares = width * height - len(shut)
    if open_squares > 12:
        raise ValueError("the board leaves more than 12 unblocked squares")
    if not on_board(start):
        raise ValueError("start must be a pair naming a board square")
    first = start[0] * width + start[1]
    if first in shut:
        raise ValueError("start names a blocked square")

    seen = {first}
    tours = 0

    def walk(row: int, col: int, stood: int) -> None:
        nonlocal tours
        if stood == open_squares:
            tours += 1
            return
        for down, across in STEPS:
            r = row + down
            c = col + across
            if r < 0 or r >= height or c < 0 or c >= width:
                continue
            key = r * width + c
            if key in shut or key in seen:
                continue
            seen.add(key)
            walk(r, c, stood + 1)
            seen.discard(key)

    walk(start[0], start[1], 1)
    return tours
