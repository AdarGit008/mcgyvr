def _validated(intervals):
    for entry in intervals:
        if (
            not isinstance(entry, list)
            or len(entry) != 2
            or not all(isinstance(n, int) and not isinstance(n, bool) for n in entry)
        ):
            raise ValueError("an interval must be a pair of integers")
        if entry[0] >= entry[1]:
            raise ValueError("lo must be strictly below hi")
    return intervals


def _canonical(intervals):
    out = []
    for lo, hi in sorted(intervals):
        if out and lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def range_algebra(a: list, b: list, op: str) -> list:
    if op not in ("union", "intersect", "subtract"):
        raise ValueError("unknown op")
    left = _canonical(_validated(a))
    right = _canonical(_validated(b))
    if op == "union":
        return _canonical(left + right)
    out = []
    if op == "intersect":
        for lo, hi in left:
            for s, e in right:
                start = max(lo, s)
                stop = min(hi, e)
                if start < stop:
                    out.append([start, stop])
        return _canonical(out)
    for lo, hi in left:
        dead = False
        for s, e in right:
            if e <= lo or s >= hi:
                continue
            if s > lo:
                out.append([lo, s])
            lo = max(lo, e)
            if lo >= hi:
                dead = True
                break
        if not dead:
            out.append([lo, hi])
    return _canonical(out)
