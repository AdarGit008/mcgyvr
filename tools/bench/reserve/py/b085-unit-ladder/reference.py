import math


def ladder_convert(rules, amount, source, goal):
    if not isinstance(amount, int) or amount < 0:
        raise ValueError("amount must be a non-negative integer")
    down = {}
    smalls = set()
    for big, small, factor in rules:
        if not isinstance(factor, int) or factor < 2:
            raise ValueError("factor must be an integer of at least 2")
        if big in down or small in smalls:
            raise ValueError("unit sits twice on the same side")
        down[big] = (small, factor)
        smalls.add(small)
    heads = [unit for unit in down if unit not in smalls]
    if len(heads) != 1:
        raise ValueError("rules must form one single ladder")
    order = [heads[0]]
    factors = []
    while order[-1] in down:
        small, factor = down[order[-1]]
        order.append(small)
        factors.append(factor)
    if len(factors) != len(down):
        raise ValueError("rules must form one single ladder")
    if source not in order or goal not in order:
        raise ValueError("unit not named by the ladder")
    si, gi = order.index(source), order.index(goal)
    step = math.prod(factors[min(si, gi) : max(si, gi)])
    if si <= gi:
        return amount * step
    if amount % step:
        raise ValueError("upward conversion does not come out whole")
    return amount // step
