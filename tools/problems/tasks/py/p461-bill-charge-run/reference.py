def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def bill_charge_run(prices: list, draw: int, target: int) -> dict:
    if not isinstance(prices, list):
        raise ValueError("prices must be a list")
    for price in prices:
        if not _whole(price) or price < 0:
            raise ValueError("every price must be a whole number of nought or more")
    if not _whole(draw) or draw < 1:
        raise ValueError("draw must be a whole number above nought")
    if not _whole(target) or target < 0:
        raise ValueError("target must be a whole number of nought or more")

    order = sorted(range(len(prices)), key=lambda slot: (prices[slot], slot))

    taken: dict[int, int] = {}
    owed = target
    bill = 0
    for slot in order:
        if owed == 0:
            break
        units = min(draw, owed)
        taken[slot] = units
        bill += units * prices[slot]
        owed -= units

    return {"slots": sorted(taken), "units": target - owed, "bill": bill, "short": owed}
