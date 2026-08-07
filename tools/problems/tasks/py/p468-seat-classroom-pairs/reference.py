def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def seat_classroom(room: dict) -> dict:
    if not isinstance(room, dict):
        raise ValueError("seat_classroom expects a mapping")
    if sorted(room) != ["apart", "cols", "pupils", "rows", "together"]:
        raise ValueError(
            "the room carries exactly rows, cols, pupils, together and apart"
        )
    down = room["rows"]
    across = room["cols"]
    if not _whole(down) or down < 1:
        raise ValueError("rows is not whole or falls below one")
    if not _whole(across) or across < 1:
        raise ValueError("cols is not whole or falls below one")

    roster = room["pupils"]
    if not isinstance(roster, list):
        raise ValueError("the pupils are not a list")
    names = []
    for pupil in roster:
        if not isinstance(pupil, str) or not pupil:
            raise ValueError("a pupil is not a non-empty string")
        if pupil in names:
            raise ValueError("two pupils share a name")
        names.append(pupil)
    desks = down * across
    if len(names) > desks:
        raise ValueError("there are more pupils than desks")
    names.sort()
    rank = {name: at for at, name in enumerate(names)}
    count = len(names)

    def read_pairs(field):
        raw = room[field]
        if not isinstance(raw, list):
            raise ValueError("a pairing list is not a list")
        found = set()
        for pair in raw:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("a pairing is not a list of two names")
            if not isinstance(pair[0], str) or not isinstance(pair[1], str):
                raise ValueError("a pairing names somebody the roster does not hold")
            if pair[0] not in rank or pair[1] not in rank:
                raise ValueError("a pairing names somebody the roster does not hold")
            first = rank[pair[0]]
            second = rank[pair[1]]
            if first == second:
                raise ValueError("a pairing names one pupil twice")
            key = min(first, second) * count + max(first, second)
            if key in found:
                raise ValueError("a pairing is listed twice in one list")
            found.add(key)
        return found

    glued = read_pairs("together")
    split = read_pairs("apart")
    if glued & split:
        raise ValueError("a pairing appears in both lists")

    partners = [[] for _ in names]
    for key in glued:
        lo, hi = divmod(key, count)
        partners[lo].append(hi)
        partners[hi].append(lo)

    def pair_key(a, b):
        return min(a, b) * count + max(a, b)

    def adjacent(a, b):
        row_a, col_a = divmod(a, across)
        row_b, col_b = divmod(b, across)
        return (row_a == row_b and abs(col_a - col_b) == 1) or (
            col_a == col_b and abs(row_a - row_b) == 1
        )

    seat_of = [-1] * desks
    desk_of = [-1] * count

    def solve(at, left):
        if at == desks:
            return left == 0
        if desks - at < left:
            return False
        row, column = divmod(at, across)
        for pupil in range(count):
            if desk_of[pupil] != -1:
                continue
            fine = True
            if column > 0 and seat_of[at - 1] != -1:
                fine = pair_key(pupil, seat_of[at - 1]) not in split
            if fine and row > 0 and seat_of[at - across] != -1:
                fine = pair_key(pupil, seat_of[at - across]) not in split
            if fine:
                for mate in partners[pupil]:
                    if desk_of[mate] != -1 and not adjacent(at, desk_of[mate]):
                        fine = False
                        break
            if not fine:
                continue
            seat_of[at] = pupil
            desk_of[pupil] = at
            if solve(at + 1, left - 1):
                return True
            seat_of[at] = -1
            desk_of[pupil] = -1
        return solve(at + 1, left)

    if not solve(0, count):
        return {"seated": False, "grid": []}
    grid = []
    for row in range(down):
        line = []
        for column in range(across):
            who = seat_of[row * across + column]
            line.append("" if who == -1 else names[who])
        grid.append(line)
    return {"seated": True, "grid": grid}
