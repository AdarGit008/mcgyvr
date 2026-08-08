def allocate_cents(total: int, weights: list[int]) -> list[int]:
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise ValueError("total must be a non-negative integer of cents")
    if not isinstance(weights, list) or not weights:
        raise ValueError("weights must be a non-empty list")
    for w in weights:
        if not isinstance(w, int) or isinstance(w, bool) or w <= 0:
            raise ValueError("every weight must be a positive integer")
    weight_sum = sum(weights)
    shares = [(total * w) // weight_sum for w in weights]
    remainders = [(total * w) % weight_sum for w in weights]
    leftover = total - sum(shares)
    order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
    for k in range(leftover):
        shares[order[k]] += 1
    return shares
