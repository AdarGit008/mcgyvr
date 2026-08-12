def tally_column(table, column):
    if not isinstance(table, list) or not table:
        raise ValueError("table must hold at least one row")
    width = len(table[0])
    bad_column = isinstance(column, bool) or not isinstance(column, int)
    if bad_column or not 0 <= column < width:
        raise ValueError("column index is outside the rows")
    count, total = 0, 0
    low, high = None, None
    for row in table:
        if len(row) != width:
            raise ValueError("rows must share one length")
        value = row[column]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("cells in the column must be numbers")
        count += 1
        total += value
        if low is None or value < low:
            low = value
        if high is None or value > high:
            high = value
    return {"count": count, "total": total, "low": low, "high": high}
