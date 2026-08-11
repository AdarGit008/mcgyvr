def root_digit(value: int) -> int:
    left = value
    while left >= 10:
        total = 0
        while left > 0:
            total += left % 10
            left = left // 10
        left = total
    return left
