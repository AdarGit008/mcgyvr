def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def kerned_run_width(text: str, widths: dict, kerns: list, tracking: int) -> int:
    if not isinstance(text, str):
        raise ValueError("kerned_run_width expects a string run")
    if not isinstance(widths, dict):
        raise ValueError("widths must be a plain mapping")
    for letter, width in widths.items():
        if not _whole(width) or width < 0:
            raise ValueError(f"a width is a whole number of zero or more: {letter}")
    if not isinstance(kerns, list):
        raise ValueError("kerns must be a table list")
    table: dict[str, int] = {}
    for row in kerns:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError("a table row is a couple and a number")
        couple, adjust = row
        if not isinstance(couple, str) or len(couple) != 2:
            raise ValueError(f"a couple is exactly two characters: {couple}")
        if not _whole(adjust):
            raise ValueError("a kern is a whole number")
        table.setdefault(couple, adjust)
    if not _whole(tracking):
        raise ValueError("tracking is a whole number")
    total = 0
    for letter in text:
        if letter not in widths:
            raise ValueError(f"no width for {letter}")
        total += widths[letter]
    for at in range(1, len(text)):
        total += tracking
        couple = text[at - 1 : at + 1]
        if couple in table:
            total += table[couple]
    if total < 0:
        raise ValueError("the run measures below zero")
    return total
