def capped_compositions(total, parts, lo, hi):
    for value in (total, parts, lo, hi):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("all arguments must be integers")
    if parts < 1:
        raise ValueError("parts must be a positive integer")
    if lo < 0 or hi < 0:
        raise ValueError("bounds must be non-negative integers")
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    if total < parts * lo or total > parts * hi:
        return 0
    ways = {0: 1}
    for _ in range(parts):
        grown = {}
        for partial, count in ways.items():
            for value in range(lo, hi + 1):
                reached = partial + value
                if reached > total:
                    break
                grown[reached] = grown.get(reached, 0) + count
        ways = grown
    return ways.get(total, 0)
