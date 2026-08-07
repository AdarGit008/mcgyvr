def split_cargo(weights: list[int]) -> list[int]:
    if not weights:
        raise ValueError("empty manifest")
    for w in weights:
        if not isinstance(w, int) or w < 1:
            raise ValueError("weights must be positive integers")
    n = len(weights)
    total = sum(weights)
    best = None
    best_key = None
    for mask in range(1, 1 << n, 2):
        picked = [i for i in range(n) if mask >> i & 1]
        forward = sum(weights[i] for i in picked)
        key = (abs(total - 2 * forward), len(picked), picked)
        if best_key is None or key < best_key:
            best_key = key
            best = picked
    return best
