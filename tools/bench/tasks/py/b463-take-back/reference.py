def take_back(values: list, target: int) -> int:
    total = 0
    taken = 0
    i = len(values) - 1
    while i >= 0 and total < target:
        total += values[i]
        taken += 1
        i -= 1
    return taken if total >= target else -1
