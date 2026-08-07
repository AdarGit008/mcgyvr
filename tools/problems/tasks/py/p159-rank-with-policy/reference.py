def rank_with_policy(scores: list, policy: str, direction: str) -> list:
    if policy not in ("dense", "gapped", "entry"):
        raise ValueError("bad policy")
    if direction not in ("asc", "desc"):
        raise ValueError("bad direction")
    if not isinstance(scores, list) or not scores:
        raise ValueError("empty scores")
    for s in scores:
        if not isinstance(s, int) or isinstance(s, bool):
            raise ValueError("non-integer score")
    sign = 1 if direction == "asc" else -1
    if policy == "entry":
        order = sorted(range(len(scores)), key=lambda i: (sign * scores[i], i))
        out = [0] * len(scores)
        for r, original in enumerate(order):
            out[original] = r + 1
        return out
    distinct = sorted(set(scores), key=lambda v: sign * v)
    rank = {}
    if policy == "dense":
        for i, v in enumerate(distinct):
            rank[v] = i + 1
    else:
        for v in distinct:
            better = sum(1 for s in scores if sign * (s - v) < 0)
            rank[v] = better + 1
    return [rank[s] for s in scores]
