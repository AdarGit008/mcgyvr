def zero_tail(value: int) -> int:
    if value == 0:
        return 1
    left = value
    zeros = 0
    while left % 10 == 0:
        zeros += 1
        left = left // 10
    return zeros
