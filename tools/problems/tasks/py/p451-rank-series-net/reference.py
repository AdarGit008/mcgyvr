def _whole(value, least: int, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < least:
        raise ValueError(f"{what} must be a whole number of at least {least}")
    return value


def rank_series_net(entries: list, bands: list) -> dict:
    if not isinstance(entries, list) or not entries:
        raise ValueError("there must be at least one entry")
    if not isinstance(bands, list) or not bands:
        raise ValueError("there must be at least one band")

    table = []
    highest = -1
    for band in bands:
        limit = _whole(band.get("limit"), 0, "a band limit")
        allowance = _whole(band.get("allowance"), 0, "a band allowance")
        if limit <= highest:
            raise ValueError("the band limits must strictly rise")
        highest = limit
        table.append((limit, allowance))

    names = set()
    standing = []
    unranked = []

    for entry in entries:
        name = entry.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("every entry needs a name")
        if name in names:
            raise ValueError(f"{name} is entered twice")
        names.add(name)

        mark = _whole(entry.get("mark"), 0, f"the mark of {name}")
        base = None
        for limit, allowance in table:
            if mark <= limit:
                base = allowance
                break
        if base is None:
            raise ValueError(f"the mark of {name} lies above every band")

        legs = entry.get("rounds")
        if not isinstance(legs, list):
            raise ValueError(f"the rounds of {name} must be a list")
        nets = []
        for leg in legs:
            gross = _whole(leg.get("gross"), 1, f"a gross score of {name}")
            weight = _whole(leg.get("weight"), 1, f"a weight of {name}")
            if weight > 200:
                raise ValueError(f"a weight of {name} is above two hundred")
            nets.append(gross - (base * weight) // 100)

        if len(nets) < 3:
            unranked.append(name)
            continue

        counted = list(range(len(nets)))
        if len(nets) > 3:
            worst = 0
            for index in range(1, len(nets)):
                if nets[index] >= nets[worst]:
                    worst = index
            counted = [index for index in counted if index != worst]
        total = sum(nets[index] for index in counted)
        best = min(nets[index] for index in counted)
        standing.append((total, best, name, counted))

    standing.sort()
    unranked.sort()

    return {
        "standings": [
            {"place": place, "name": name, "total": total, "counted": counted}
            for place, (total, best, name, counted) in enumerate(standing, start=1)
        ],
        "unranked": unranked,
    }
