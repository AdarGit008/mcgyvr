def stamp_table(dies: list) -> dict:
    table = {}
    for fragment, price in dies:
        if not isinstance(fragment, str) or not fragment:
            raise ValueError("a die fragment must be a non-empty string")
        if isinstance(price, bool) or not isinstance(price, int) or price <= 0:
            raise ValueError("a die price must be a positive integer")
        if fragment in table:
            raise ValueError("die listed twice: " + fragment)
        table[fragment] = price
    return table


def stamp_cover(label: str, dies: list) -> int:
    if not isinstance(label, str) or not label:
        raise ValueError("the label must be a non-empty string")
    table = stamp_table(dies)
    best = [0] + [None] * len(label)
    for end in range(1, len(label) + 1):
        for fragment, price in table.items():
            start = end - len(fragment)
            if start < 0 or best[start] is None:
                continue
            if label[start:end] != fragment:
                continue
            cost = best[start] + price
            if best[end] is None or cost < best[end]:
                best[end] = cost
    if best[-1] is None:
        raise ValueError("no sequence of dies spells the label")
    return best[-1]
