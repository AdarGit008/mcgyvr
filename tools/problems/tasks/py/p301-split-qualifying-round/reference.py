def split_qualifying_round(entrants: list[str]) -> dict:
    if not isinstance(entrants, list):
        raise ValueError("split_qualifying_round expects a list of entrants")
    if len(entrants) < 2:
        raise ValueError("a field needs at least two entrants")
    seen: set[str] = set()
    for name in entrants:
        if not isinstance(name, str):
            raise ValueError("an entrant name is a string")
        if name in seen:
            raise ValueError(f"listed twice: {name}")
        seen.add(name)
    draw = 1
    while draw * 2 <= len(entrants):
        draw *= 2
    surplus = len(entrants) - draw
    walking = len(entrants) - 2 * surplus
    direct = entrants[:walking]
    group = entrants[walking:]
    qualifying = [[group[at], group[len(group) - 1 - at]] for at in range(surplus)]
    return {"direct": direct, "qualifying": qualifying}
