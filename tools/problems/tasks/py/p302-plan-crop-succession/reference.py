def plan_crop_succession(
    last_sown: list[str],
    follows: list[list[str]],
    order: list[str],
    seasons: int,
) -> list[list[str]]:
    if not isinstance(last_sown, list) or not last_sown:
        raise ValueError("the plot list must be a non-empty list")
    for crop in last_sown:
        if not isinstance(crop, str) or not crop:
            raise ValueError("every plot carries a crop name")
    if not isinstance(follows, list):
        raise ValueError("the table must be a list")
    edges = set()
    for row in follows:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("every table row is a pair")
        for crop in row:
            if not isinstance(crop, str) or not crop:
                raise ValueError("every table entry is a crop name")
        key = (row[0], row[1])
        if key in edges:
            raise ValueError("the table states one pair twice")
        edges.add(key)
    if not isinstance(order, list) or not order:
        raise ValueError("the ranking must be a non-empty list")
    ranked = set()
    for crop in order:
        if not isinstance(crop, str) or not crop:
            raise ValueError("every ranked entry is a crop name")
        if crop in ranked:
            raise ValueError("the ranking repeats a crop")
        ranked.add(crop)
    for crop in last_sown:
        if crop not in ranked:
            raise ValueError("unranked crop on a plot")
    for row in follows:
        for crop in row:
            if crop not in ranked:
                raise ValueError("unranked crop in the table")
    if isinstance(seasons, bool) or not isinstance(seasons, int) or seasons < 1:
        raise ValueError("the season count must be a whole number above zero")

    plots = len(last_sown)
    allowance = -(-plots // 2)
    plan: list[list[str]] = [[] for _ in last_sown]
    for season in range(seasons):
        drilled: dict[str, int] = {}
        for plot in range(plots):
            before = last_sown[plot] if season == 0 else plan[plot][season - 1]
            if season == 0:
                earlier = None
            elif season == 1:
                earlier = last_sown[plot]
            else:
                earlier = plan[plot][season - 2]
            chosen = None
            for crop in order:
                if (before, crop) not in edges:
                    continue
                if crop == before or crop == earlier:
                    continue
                if drilled.get(crop, 0) >= allowance:
                    continue
                chosen = crop
                break
            if chosen is None:
                return []
            plan[plot].append(chosen)
            drilled[chosen] = drilled.get(chosen, 0) + 1
    return plan
