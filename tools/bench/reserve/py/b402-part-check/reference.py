def part_check(total: int, parts: list, tolerance: int) -> bool:
    summed = 0
    for part in parts:
        summed += part
    return abs(total - summed) <= tolerance
