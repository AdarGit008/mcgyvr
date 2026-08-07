def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def plan_exhibit_tour(stops: list, budget: int) -> dict:
    if not isinstance(stops, list):
        raise ValueError("plan_exhibit_tour expects a list of stops")
    if not _whole(budget) or budget < 0:
        raise ValueError("the budget is not whole or falls below nought")

    halls = []
    seen = set()
    for stop in stops:
        if not isinstance(stop, dict):
            raise ValueError("a stop is not a mapping")
        if sorted(stop) != ["name", "stay", "walk", "worth"]:
            raise ValueError("a stop's keys are not exactly the four named")
        name = stop["name"]
        if not isinstance(name, str) or name == "":
            raise ValueError("a name is not a non-empty string")
        if name in seen:
            raise ValueError("a name is repeated")
        seen.add(name)
        walk = stop["walk"]
        if not _whole(walk) or walk < 0:
            raise ValueError("a walk is not whole or falls below nought")
        stay = stop["stay"]
        if not _whole(stay) or stay < 1:
            raise ValueError("a stay is not whole or falls below one")
        worth = stop["worth"]
        if not _whole(worth) or worth < 0:
            raise ValueError("a worth is not whole or falls below nought")
        halls.append({"name": name, "walk": walk, "stay": stay, "worth": worth})

    reach = []
    paced = 0
    for hall in halls:
        paced += hall["walk"]
        reach.append(paced)

    def worth_of(picks):
        return sum(halls[index]["worth"] for index in picks)

    # Same last stop and same total stay means the same minutes, so only
    # worth, then count, then the picks themselves decide a cell.
    def finer(left, right):
        return (-worth_of(left), len(left), left) < (
            -worth_of(right),
            len(right),
            right,
        )

    states = [{} for _ in halls]
    for i, hall in enumerate(halls):

        def offer(stay_total, picks, i=i):
            if reach[i] + stay_total > budget:
                return
            held = states[i].get(stay_total)
            if held is None or finer(picks, held):
                states[i][stay_total] = picks

        offer(hall["stay"], [i])
        for j in range(i):
            for stay_total, picks in states[j].items():
                offer(stay_total + hall["stay"], picks + [i])

    best_picks = []
    best_worth = 0
    best_minutes = 0
    for i in range(len(halls)):
        for stay_total, picks in states[i].items():
            worth = worth_of(picks)
            minutes = reach[i] + stay_total
            if (-worth, minutes, len(picks), picks) < (
                -best_worth,
                best_minutes,
                len(best_picks),
                best_picks,
            ):
                best_picks = picks
                best_worth = worth
                best_minutes = minutes

    return {
        "names": [halls[index]["name"] for index in best_picks],
        "worth": best_worth,
        "minutes": best_minutes,
    }
