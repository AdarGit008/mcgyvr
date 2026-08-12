def part_ways(left: list[str], right: list[str]) -> int:
    shorter = len(left) if len(left) < len(right) else len(right)
    for i in range(shorter):
        if left[i] != right[i]:
            return i
    if len(left) != len(right):
        return shorter
    return -1
