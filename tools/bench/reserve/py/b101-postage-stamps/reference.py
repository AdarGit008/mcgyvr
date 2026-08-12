"""The fewest stamps that make exact postage from given denominations."""


def fewest_stamps(postage, denominations):
    if isinstance(postage, bool) or not isinstance(postage, int):
        raise ValueError("postage must be a non-negative integer")
    if postage < 0:
        raise ValueError("postage must be a non-negative integer")
    if not isinstance(denominations, list) or not denominations:
        raise ValueError("denominations must be a non-empty list")
    seen = set()
    for stamp in denominations:
        if isinstance(stamp, bool) or not isinstance(stamp, int):
            raise ValueError("denominations must be positive integers")
        if stamp <= 0:
            raise ValueError("denominations must be positive integers")
        if stamp in seen:
            raise ValueError("denominations must not repeat")
        seen.add(stamp)
    unreached = postage + 1
    best = [unreached] * (postage + 1)
    best[0] = 0
    for value in range(1, postage + 1):
        for stamp in denominations:
            if stamp <= value and best[value - stamp] + 1 < best[value]:
                best[value] = best[value - stamp] + 1
    if best[postage] == unreached:
        raise ValueError("the postage cannot be made exactly")
    descending = sorted(denominations, reverse=True)
    stamps = []
    value = postage
    while value > 0:
        for stamp in descending:
            if stamp <= value and best[value - stamp] == best[value] - 1:
                stamps.append(stamp)
                value -= stamp
                break
    return {"count": len(stamps), "stamps": stamps}
