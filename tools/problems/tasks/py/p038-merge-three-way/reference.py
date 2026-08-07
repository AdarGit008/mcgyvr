_MISSING = object()


def merge_three_way(base: dict, ours: dict, theirs: dict) -> dict:
    for side in (base, ours, theirs):
        if not isinstance(side, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in side.items()
        ):
            raise ValueError("each argument must be a mapping of strings to strings")
    merged = {}
    conflicts = []
    for key in sorted(set(base) | set(ours) | set(theirs)):
        b = base.get(key, _MISSING)
        o = ours.get(key, _MISSING)
        t = theirs.get(key, _MISSING)
        if o == b and t == b:
            pick = b
        elif o == b:
            pick = t
        elif t == b:
            pick = o
        elif o == t:
            pick = o
        else:
            conflicts.append(key)
            pick = b
        if pick is not _MISSING:
            merged[key] = pick
    return {"merged": merged, "conflicts": conflicts}
