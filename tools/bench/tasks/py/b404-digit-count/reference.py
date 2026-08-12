def digit_count(value: int) -> int:
    left = -value if value < 0 else value
    if left == 0:
        return 1
    digits = 0
    while left > 0:
        digits += 1
        left = left // 10
    return digits
