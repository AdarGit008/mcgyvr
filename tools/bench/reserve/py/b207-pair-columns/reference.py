"""Lay two blocks of text side by side with a fixed gap between them."""


def pair_columns(left: list, right: list, gap: int) -> list:
    if isinstance(gap, bool) or not isinstance(gap, int) or gap < 0:
        raise ValueError("gap must be a non-negative integer")
    width = 0
    for line in left:
        width = max(width, len(line))
    rows = max(len(left), len(right))
    laid = []
    for row in range(rows):
        near = left[row] if row < len(left) else ""
        far = right[row] if row < len(right) else ""
        line = near + " " * (width - len(near) + gap) + far
        while line.endswith(" "):
            line = line[:-1]
        laid.append(line)
    return laid
