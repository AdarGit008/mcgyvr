def can_hop(pond: list, origin: list, dest: list) -> bool:
    if (
        not isinstance(pond, list)
        or len(pond) != 5
        or any(not isinstance(row, str) or len(row) != 5 for row in pond)
    ):
        raise ValueError("malformed pond")
    for square in (origin, dest):
        if (
            not isinstance(square, list)
            or len(square) != 2
            or not all(
                isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 4
                for n in square
            )
        ):
            raise ValueError("a square must be a pair of integers between 0 and 4")
    if pond[origin[0]][origin[1]] == ".":
        return False
    if pond[dest[0]][dest[1]] != ".":
        return False
    dr = dest[0] - origin[0]
    dc = dest[1] - origin[1]
    if abs(dr) + abs(dc) == 1:
        return True
    vault_shape = (
        (abs(dr) == 2 and dc == 0)
        or (dr == 0 and abs(dc) == 2)
        or (abs(dr) == 2 and abs(dc) == 2)
    )
    if not vault_shape:
        return False
    return pond[origin[0] + dr // 2][origin[1] + dc // 2] != "."
