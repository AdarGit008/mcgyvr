def pair_sums(readings: list) -> list:
    totals = []
    for i in range(1, len(readings)):
        totals.append(readings[i - 1] + readings[i])
    return totals
