def sum_range(first: int, last: int) -> int:
    total = 0
    for value in range(first, last + 1):
        total += value
    return total
