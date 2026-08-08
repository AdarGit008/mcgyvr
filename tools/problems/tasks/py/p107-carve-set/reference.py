def carve_set(steps: list) -> list:
    held = []
    for verb, lo, hi in steps:
        if verb not in ("add", "cut"):
            raise ValueError("unknown verb")
        if not all(isinstance(n, int) and not isinstance(n, bool) for n in (lo, hi)):
            raise ValueError("bounds must be integers")
        if lo >= hi:
            raise ValueError("lo must be strictly below hi")
        after = []
        if verb == "add":
            start, stop = lo, hi
            for a, b in held:
                if b < start or a > stop:
                    after.append([a, b])
                else:
                    start = min(start, a)
                    stop = max(stop, b)
            after.append([start, stop])
            after.sort()
        else:
            for a, b in held:
                if b <= lo or a >= hi:
                    after.append([a, b])
                else:
                    if a < lo:
                        after.append([a, lo])
                    if hi < b:
                        after.append([hi, b])
        held = after
    return held
