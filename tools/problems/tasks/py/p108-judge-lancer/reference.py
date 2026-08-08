def judge_lancer(board: list, side: str, origin: list, dest: list) -> str:
    if (
        not isinstance(board, list)
        or len(board) != 7
        or any(
            not isinstance(row, str)
            or len(row) != 7
            or any(ch not in "WB." for ch in row)
            for row in board
        )
    ):
        raise ValueError("malformed board")
    if side not in ("W", "B"):
        raise ValueError("bad side")
    for square in (origin, dest):
        if (
            not isinstance(square, list)
            or len(square) != 2
            or not all(
                isinstance(n, int) and not isinstance(n, bool) for n in square
            )
        ):
            raise ValueError("a square must be a pair of integers")

    def inside(square):
        return 0 <= square[0] < 7 and 0 <= square[1] < 7

    if not inside(origin) or not inside(dest):
        return "off_board"
    if board[origin[0]][origin[1]] != side:
        return "no_piece"
    dr = dest[0] - origin[0]
    dc = dest[1] - origin[1]
    span = abs(dr) + abs(dc)
    if (dr != 0 and dc != 0) or span < 1 or span > 3:
        return "bad_line"
    sr = (dr > 0) - (dr < 0)
    sc = (dc > 0) - (dc < 0)
    for k in range(1, span):
        if board[origin[0] + sr * k][origin[1] + sc * k] != ".":
            return "blocked"
    landing = board[dest[0]][dest[1]]
    if landing == side:
        return "own_piece"
    if landing != "." and span < 2:
        return "too_close"
    return "ok"
