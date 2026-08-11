def gear_ratio(first: int, second: int) -> str:
    if second == 0:
        raise ValueError("the second count must not be nothing")
    left = first
    right = second
    while right != 0:
        rest = left % right
        left = right
        right = rest
    share = 1 if left == 0 else left
    return str(first // share) + ":" + str(second // share)
