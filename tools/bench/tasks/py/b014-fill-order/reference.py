def fill_order(sources, needed):
    if isinstance(needed, bool) or not isinstance(needed, int) or needed < 1:
        raise ValueError("needed must be a positive integer")
    if not isinstance(sources, list):
        raise ValueError("sources must be a list")
    available = 0
    for source in sources:
        if not isinstance(source, list) or len(source) != 2:
            raise ValueError("every source is a [cost, stock] pair")
        unit_cost, stock = source
        if (
            isinstance(unit_cost, bool)
            or not isinstance(unit_cost, int)
            or unit_cost < 1
        ):
            raise ValueError("cost must be a positive integer")
        if isinstance(stock, bool) or not isinstance(stock, int) or stock < 1:
            raise ValueError("stock must be a positive integer")
        available += stock
    if available < needed:
        raise ValueError("sources cannot cover the order")
    order = sorted(range(len(sources)), key=lambda index: sources[index][0])
    taken = [0] * len(sources)
    cost = 0
    remaining = needed
    for index in order:
        if remaining == 0:
            break
        draw = min(sources[index][1], remaining)
        taken[index] = draw
        cost += draw * sources[index][0]
        remaining -= draw
    leftover = []
    for index in range(len(sources)):
        leftover.append(sources[index][1] - taken[index])
    return {"cost": cost, "taken": taken, "leftover": leftover}
