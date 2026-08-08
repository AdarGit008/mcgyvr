def order_color_report(
    neighbours: list[list[int]], visit_order: list[int]
) -> list[list[int]]:
    if not isinstance(neighbours, list) or not neighbours:
        raise ValueError("there must be at least one transmitter")
    count = len(neighbours)
    for node, clashes in enumerate(neighbours):
        if not isinstance(clashes, list):
            raise ValueError("each transmitter needs a list of clashes")
        for other in clashes:
            if isinstance(other, bool) or not isinstance(other, int):
                raise ValueError("a clash must name a transmitter number")
            if other < 0 or other >= count:
                raise ValueError("a clash names a transmitter that does not exist")
            if other == node:
                raise ValueError("a transmitter cannot clash with itself")
            if node not in neighbours[other]:
                raise ValueError("a clash is recorded on one side only")
    if not isinstance(visit_order, list) or len(visit_order) != count:
        raise ValueError("the walking sequence must be every transmitter once")
    seen = set()
    for node in visit_order:
        if isinstance(node, bool) or not isinstance(node, int):
            raise ValueError("the walking sequence must be every transmitter once")
        if node < 0 or node >= count or node in seen:
            raise ValueError("the walking sequence must be every transmitter once")
        seen.add(node)

    channel = [-1] * count
    for node in visit_order:
        taken = {channel[other] for other in neighbours[node] if channel[other] >= 0}
        pick = 0
        while pick in taken:
            pick += 1
        channel[node] = pick
    return [channel, [len(set(channel))]]
