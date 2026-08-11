def thaw_row(row: str, steps: int) -> str:
    if not isinstance(row, str) or not row:
        raise ValueError("thaw_row expects a non-empty string row")
    if any(cell not in "#." for cell in row):
        raise ValueError("row may hold only # and . cells")
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0:
        raise ValueError("steps must be a non-negative whole number")
    cells = row
    for _ in range(steps):
        padded = "." + cells + "."
        cells = "".join("#" if padded[i : i + 3] == "###" else "." for i in range(len(cells)))
    return cells
