def quota_share(budget: int, weights: list) -> list:
    total = sum(weights)
    if total == 0:
        return [0 for _ in weights]
    shares = [budget * weight // total for weight in weights]
    best = 0
    for i in range(1, len(weights)):
        if weights[i] > weights[best]:
            best = i
    shares[best] += budget - sum(shares)
    return shares
