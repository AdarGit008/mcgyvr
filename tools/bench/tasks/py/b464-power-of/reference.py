def power_of(base: int, power: int) -> int:
    if power < 0:
        raise ValueError("a power cannot fall below nothing")
    total = 1
    for _ in range(power):
        total *= base
    return total
