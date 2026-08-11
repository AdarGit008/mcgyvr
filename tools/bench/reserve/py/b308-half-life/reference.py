def half_life(count: int, steps: int) -> int:
    left = count
    for _ in range(steps):
        left = left // 2
    return left
