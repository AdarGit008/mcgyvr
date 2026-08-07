def _price_of(row):
    price = row.get("price")
    if isinstance(price, bool) or not isinstance(price, int) or price < 1:
        raise ValueError("a price must be a whole number of pence, one or more")
    return price


def _code_of(row):
    if not isinstance(row, dict):
        raise ValueError("everything on sale must be a record")
    code = row.get("code")
    if not isinstance(code, str) or code == "":
        raise ValueError("a code must be a non-empty string")
    return code


def cheapest_tray(items: list, bundles: list, needed: list) -> dict:
    if (
        not isinstance(items, list)
        or not isinstance(bundles, list)
        or not isinstance(needed, list)
    ):
        raise ValueError("items, bundles and the requirement must all be lists")
    if len(items) + len(bundles) > 14:
        raise ValueError("more than fourteen things on sale is too many to search")

    on_sale = set()
    sold = set()
    options = []
    for row in items:
        code = _code_of(row)
        if code in on_sale:
            raise ValueError("two things on sale share the code " + code)
        on_sale.add(code)
        sold.add(code)
        options.append((code, _price_of(row), [code]))
    for row in bundles:
        code = _code_of(row)
        if code in on_sale:
            raise ValueError("two things on sale share the code " + code)
        on_sale.add(code)
        holds = row.get("holds")
        if not isinstance(holds, list) or not holds:
            raise ValueError("bundle " + code + " holds nothing")
        for held in holds:
            if held not in sold:
                raise ValueError("bundle " + code + " holds an unknown code")
        options.append((code, _price_of(row), holds))

    wanted = {}
    for code in needed:
        if code not in sold:
            raise ValueError("no item sells the required code " + str(code))
        if code in wanted:
            raise ValueError("the code " + code + " is required twice")
        wanted[code] = len(wanted)

    masks = []
    for _code, _price, holds in options:
        mask = 0
        for held in holds:
            if held in wanted:
                mask |= 1 << wanted[held]
        masks.append(mask)

    full = (1 << len(wanted)) - 1
    best = None
    for subset in range(1 << len(options)):
        mask = 0
        cost = 0
        picks = []
        for index in range(len(options)):
            if subset & (1 << index):
                mask |= masks[index]
                cost += options[index][1]
                picks.append(options[index][0])
        if mask != full:
            continue
        picks.sort()
        key = (cost, len(picks), picks)
        if best is None or key < best:
            best = key

    if best is None:
        return {"total": 0, "picks": []}
    return {"total": best[0], "picks": best[2]}
