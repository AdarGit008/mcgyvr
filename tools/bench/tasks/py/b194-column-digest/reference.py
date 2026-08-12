"""Summarize one column of a ragged sheet."""

import math


def column_digest(rows: list, column: int) -> dict:
    cells = [row[column] for row in rows if len(row) > column]
    if not cells:
        return {"count": 0, "min": 0, "max": 0, "mean": 0, "median": 0}
    order = sorted(cells)
    middle = len(order) // 2
    median = order[middle] if len(order) % 2 == 1 else (order[middle - 1] + order[middle]) / 2
    two_places = lambda value: math.floor(value * 100 + 0.5) / 100
    return {
        "count": len(cells),
        "min": order[0],
        "max": order[-1],
        "mean": two_places(sum(cells) / len(cells)),
        "median": two_places(median),
    }
