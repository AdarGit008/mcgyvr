def load_vans(parcels: list[int]) -> list[int]:
    if not parcels:
        raise ValueError("no parcels")
    for p in parcels:
        if not isinstance(p, int) or p < 1:
            raise ValueError("weights must be positive integers")
    order = sorted(range(len(parcels)), key=lambda i: (-parcels[i], i))
    first = 0
    second = 0
    for i in order:
        if first <= second:
            first += parcels[i]
        else:
            second += parcels[i]
    return [first, second]
