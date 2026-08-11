def base_write(value: int, base: int) -> str:
    if base < 2 or base > 16:
        raise ValueError("the base must stand between two and sixteen")
    figures = "0123456789abcdef"
    if value == 0:
        return "0"
    left = value
    out = ""
    while left > 0:
        out = figures[left % base] + out
        left = left // base
    return out
