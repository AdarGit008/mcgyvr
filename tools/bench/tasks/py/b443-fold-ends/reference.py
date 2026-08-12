def fold_ends(values: list) -> list:
    totals = []
    low = 0
    high = len(values) - 1
    while low < high:
        totals.append(values[low] + values[high])
        low += 1
        high -= 1
    if low == high:
        totals.append(values[low])
    return totals
