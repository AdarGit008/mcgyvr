def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def plan_cut_list(bars: list, orders: list, kerf: int, keep: int) -> dict:
    if not isinstance(bars, list):
        raise ValueError("plan_cut_list expects a list of bars")
    if not isinstance(orders, list):
        raise ValueError("the orders are not a list")
    if not _whole(kerf) or kerf < 0:
        raise ValueError("the kerf is not whole or falls below nought")
    if not _whole(keep) or keep < 0:
        raise ValueError("the keep is not whole or falls below nought")
    for bar in bars:
        if not _whole(bar) or bar < 1:
            raise ValueError("a bar is not whole or falls below one")

    wanted = []
    named = set()
    for order in orders:
        if not isinstance(order, dict):
            raise ValueError("an order is not a mapping")
        if sorted(order) != ["count", "length"]:
            raise ValueError("an order's keys are not exactly length and count")
        length = order["length"]
        if not _whole(length) or length < 1:
            raise ValueError("a length is not whole or falls below one")
        if length in named:
            raise ValueError("a length is named by two orders")
        named.add(length)
        count = order["count"]
        if not _whole(count) or count < 1:
            raise ValueError("a count is not whole or falls below one")
        wanted.extend([length] * count)
    wanted.sort(reverse=True)

    still_on = list(bars)
    layout = [[] for _ in bars]
    short = []
    for piece in wanted:
        cut = False
        for index, room in enumerate(still_on):
            if piece <= room:
                layout[index].append(piece)
                rest = room - piece - kerf
                still_on[index] = rest if rest > 0 else 0
                cut = True
                break
        if not cut:
            short.append(piece)

    offcuts = []
    scrap = 0
    for rest in still_on:
        if rest <= 0:
            continue
        if rest >= keep:
            offcuts.append(rest)
        else:
            scrap += rest

    return {"layout": layout, "offcuts": offcuts, "scrap": scrap, "short": short}
