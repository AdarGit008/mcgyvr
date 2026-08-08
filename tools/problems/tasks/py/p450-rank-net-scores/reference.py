TABLE = ((4, 0), (9, 3), (14, 6), (19, 10), (28, 15))


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def rank_net_scores(field: list) -> list:
    if not isinstance(field, list) or not field:
        raise ValueError("the field must be a list with at least one competitor")

    rows = []
    names = set()
    for entry in field:
        name = entry.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("every competitor needs a name")
        if name in names:
            raise ValueError(f"{name} is entered twice")
        names.add(name)

        gross = entry.get("gross")
        if not _whole(gross) or gross < 1:
            raise ValueError(f"the gross score of {name} is not a whole number")
        mark = entry.get("mark")
        if not _whole(mark) or mark < 0 or mark > 28:
            raise ValueError(f"the mark of {name} is outside 0 to 28")

        allowance = next(earns for top, earns in TABLE if mark <= top)
        rows.append((gross - allowance, gross, name))

    rows.sort()
    return [
        {"place": place, "name": name, "net": net}
        for place, (net, gross, name) in enumerate(rows, start=1)
    ]
