"""Cheapest exact fulfilment of an order from priced packs."""


def cheapest_packs(order: int, packs: list) -> int:
    if isinstance(order, bool) or not isinstance(order, int) or order < 0:
        raise ValueError("order must be a non-negative integer")
    if not isinstance(packs, list) or not packs:
        raise ValueError("at least one pack is required")
    for size, price in packs:
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError("pack size must be a positive integer")
        if isinstance(price, bool) or not isinstance(price, int) or price < 0:
            raise ValueError("pack price must be a non-negative integer")
    best = [None] * (order + 1)
    best[0] = 0
    for units in range(1, order + 1):
        for size, price in packs:
            if size > units or best[units - size] is None:
                continue
            cost = best[units - size] + price
            if best[units] is None or cost < best[units]:
                best[units] = cost
    return -1 if best[order] is None else best[order]
