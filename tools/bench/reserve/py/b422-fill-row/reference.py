def blank_row(width: int) -> list:
    if width < 0:
        raise ValueError("a width cannot be below nothing")
    return [0] * width


def fill_rows(rows: int, width: int) -> list:
    """A grid of blank rows, each one its own row."""
    return [blank_row(width) for _ in range(rows)]
