import re


def layout_columns(rows: list[list[str]], aligns: str) -> list[str]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty table")
    if not isinstance(aligns, str) or re.fullmatch(r"[lrc]+", aligns) is None:
        raise ValueError("bad alignment spec")
    for row in rows:
        if not isinstance(row, list) or len(row) != len(aligns):
            raise ValueError("row width does not match the spec")
        for cell in row:
            if not isinstance(cell, str):
                raise ValueError("cell is not a string")
    widths = [max(len(row[i]) for row in rows) for i in range(len(aligns))]
    lines = []
    for row in rows:
        parts = []
        for i, cell in enumerate(row):
            pad = widths[i] - len(cell)
            if aligns[i] == "l":
                parts.append(cell + " " * pad)
            elif aligns[i] == "r":
                parts.append(" " * pad + cell)
            else:
                left = pad // 2
                parts.append(" " * left + cell + " " * (pad - left))
        lines.append("  ".join(parts).rstrip())
    return lines
