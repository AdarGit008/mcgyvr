AROUND = [
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
]


def _check_board(board):
    if not isinstance(board, list):
        raise ValueError("the board must be a list of lines")
    if len(board) == 0:
        raise ValueError("the board must hold at least one line")
    span = None
    for line in board:
        if not isinstance(line, str):
            raise ValueError("every line must be a string")
        if len(line) == 0:
            raise ValueError("a line must not be empty")
        if span is None:
            span = len(line)
        elif len(line) != span:
            raise ValueError("the lines differ in length")
        for symbol in line:
            if symbol not in ("*", "-"):
                raise ValueError("a symbol is neither a star nor a dash")
    return len(board), span


def open_sweep_cascade(board: list, origin: list) -> dict:
    tall, span = _check_board(board)
    if not isinstance(origin, list) or len(origin) != 2:
        raise ValueError("the origin must be a pair")
    for part in origin:
        if not isinstance(part, int) or isinstance(part, bool):
            raise ValueError("the origin must be whole numbers")
    line, spot = origin[0], origin[1]
    if line < 0 or line >= tall or spot < 0 or spot >= span:
        raise ValueError("the origin falls outside the board")

    def tally_at(down, across):
        total = 0
        for step_down, step_across in AROUND:
            near_down = down + step_down
            near_across = across + step_across
            if 0 <= near_down < tall and 0 <= near_across < span:
                if board[near_down][near_across] == "*":
                    total += 1
        return total

    shown = [[None] * span for _ in range(tall)]
    if board[line][spot] == "*":
        view = []
        for down in range(tall):
            view.append(
                "".join(
                    "!" if (down, across) == (line, spot) else "?"
                    for across in range(span)
                )
            )
        return {"view": view, "opened": 0, "struck": True}

    opened = 0
    waiting = [(line, spot)]
    shown[line][spot] = tally_at(line, spot)
    while waiting:
        down, across = waiting.pop()
        opened += 1
        if shown[down][across] != 0:
            continue
        for step_down, step_across in AROUND:
            near_down = down + step_down
            near_across = across + step_across
            if not (0 <= near_down < tall and 0 <= near_across < span):
                continue
            if shown[near_down][near_across] is not None:
                continue
            if board[near_down][near_across] == "*":
                continue
            shown[near_down][near_across] = tally_at(near_down, near_across)
            waiting.append((near_down, near_across))
    view = []
    for down in range(tall):
        view.append(
            "".join(
                "?" if shown[down][across] is None else str(shown[down][across])
                for across in range(span)
            )
        )
    return {"view": view, "opened": opened, "struck": False}
