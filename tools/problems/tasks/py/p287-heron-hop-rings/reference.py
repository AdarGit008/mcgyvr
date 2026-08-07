HOPS = (
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
    (-3, 0),
    (3, 0),
    (0, -3),
    (0, 3),
)


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def reach_by_hops(
    across: int,
    down: int,
    start: list[int],
    marsh: list[list[int]],
    hops: int,
) -> list[int]:
    if not _whole(across) or across < 1:
        raise ValueError("across must be an integer of at least 1")
    if not _whole(down) or down < 1:
        raise ValueError("down must be an integer of at least 1")
    if not _whole(hops) or hops < 0:
        raise ValueError("hops must be an integer of at least 0")

    def on_fen(square: object) -> bool:
        return (
            isinstance(square, list)
            and len(square) == 2
            and _whole(square[0])
            and _whole(square[1])
            and 0 <= square[0] < down
            and 0 <= square[1] < across
        )

    if not isinstance(marsh, list):
        raise ValueError("marsh must be a list")
    wet: set[int] = set()
    for square in marsh:
        if not on_fen(square):
            raise ValueError("a marsh square must be a pair naming a fen square")
        key = square[0] * across + square[1]
        if key in wet:
            raise ValueError("marsh names the same square twice")
        wet.add(key)
    if not on_fen(start):
        raise ValueError("start must be a pair naming a fen square")
    first = start[0] * across + start[1]
    if first in wet:
        raise ValueError("start names a marsh square")

    rings = [0] * (hops + 1)
    seen = {first}
    edge = [(start[0], start[1])]
    rings[0] = 1
    for ring in range(1, hops + 1):
        following: list[tuple[int, int]] = []
        for row, col in edge:
            for step_down, step_across in HOPS:
                r = row + step_down
                c = col + step_across
                if r < 0 or r >= down or c < 0 or c >= across:
                    continue
                key = r * across + c
                if key in wet or key in seen:
                    continue
                seen.add(key)
                following.append((r, c))
        rings[ring] = len(following)
        edge = following
    return rings
