"""Pivot a flat list of [row, column, amount] entries into a dense table.

Row and column labels are ordered by their descending totals, ties
alphabetical; the matrix holds sums with zeros where no entry lands; the
margins carry row, column and grand totals, a count of the truly blank
cells, and each row's leading column.
"""


def pivot_margins(entries: list) -> dict:
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")
    sums = {}
    row_sums = {}
    col_sums = {}
    for entry in entries:
        if not isinstance(entry, list) or len(entry) != 3:
            raise ValueError("each entry is a [row, column, amount] triple")
        row, col, amount = entry
        if not isinstance(row, str) or row == "":
            raise ValueError("row label must be a non-empty string")
        if not isinstance(col, str) or col == "":
            raise ValueError("column label must be a non-empty string")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError("amount must be an integer")
        sums[(row, col)] = sums.get((row, col), 0) + amount
        row_sums[row] = row_sums.get(row, 0) + amount
        col_sums[col] = col_sums.get(col, 0) + amount
    rows = sorted(row_sums, key=lambda label: (-row_sums[label], label))
    cols = sorted(col_sums, key=lambda label: (-col_sums[label], label))
    cells = []
    row_totals = []
    col_totals = [0] * len(cols)
    leaders = []
    grand = 0
    blanks = 0
    for row in rows:
        line = []
        line_total = 0
        lead_at = 0
        for index, col in enumerate(cols):
            if (row, col) not in sums:
                blanks += 1
            value = sums.get((row, col), 0)
            line.append(value)
            line_total += value
            col_totals[index] += value
            if value > line[lead_at]:
                lead_at = index
        cells.append(line)
        row_totals.append(line_total)
        leaders.append(cols[lead_at])
        grand += line_total
    return {
        "rows": rows,
        "cols": cols,
        "cells": cells,
        "row_totals": row_totals,
        "col_totals": col_totals,
        "grand": grand,
        "blanks": blanks,
        "leaders": leaders,
    }
