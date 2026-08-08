ROWS = [
    ([0, 4, 7], "major"),
    ([0, 3, 7], "minor"),
    ([0, 3, 6], "diminished"),
    ([0, 4, 8], "augmented"),
    ([0, 5, 7], "quartal"),
    ([0, 2, 6], "narrow"),
    ([0, 4, 7, 11], "major seventh"),
    ([0, 4, 7, 10], "dominant seventh"),
    ([0, 3, 7, 10], "minor seventh"),
    ([0, 3, 6, 9], "shrunk seventh"),
]


def name_triad_stack(marks: list[int]) -> dict:
    if not isinstance(marks, list) or not marks:
        raise ValueError("the argument must be a list holding at least one mark")
    classes = set()
    for mark in marks:
        if not isinstance(mark, int) or isinstance(mark, bool):
            raise ValueError("a pitch mark must be a whole number")
        classes.add(mark % 12)
    stack = sorted(classes)
    if len(stack) < 3:
        raise ValueError("the stack holds fewer than three classes")
    best_row = -1
    best_base = -1
    for base in stack:
        shape = sorted((one - base) % 12 for one in stack)
        for row, (wanted, _) in enumerate(ROWS):
            if wanted != shape:
                continue
            if best_row == -1 or row < best_row:
                best_row = row
                best_base = base
            break
    if best_row == -1:
        return {"base": -1, "name": "unknown"}
    return {"base": best_base, "name": ROWS[best_row][1]}
