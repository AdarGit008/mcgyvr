def spread_night_duty(
    crew: list[str], weights: list[int], away: list[list[str]]
) -> list[str]:
    if not isinstance(crew, list) or not crew:
        raise ValueError("the crew must hold at least one person")
    known: set[str] = set()
    for name in crew:
        if not isinstance(name, str) or not name:
            raise ValueError("a crew name must be a non-empty string")
        if name == "?":
            raise ValueError("the mark ? is not a crew name")
        if name in known:
            raise ValueError("the crew repeats a name")
        known.add(name)
    if not isinstance(weights, list) or not weights:
        raise ValueError("there must be at least one night")
    for weight in weights:
        if weight not in (1, 2) or isinstance(weight, bool):
            raise ValueError("a night weighs 1 or 2")
    if not isinstance(away, list) or len(away) != len(weights):
        raise ValueError("away must run the same length as weights")
    for entry in away:
        if not isinstance(entry, list):
            raise ValueError("an away entry must be a list")
        for name in entry:
            if not isinstance(name, str) or name not in known:
                raise ValueError("an away entry names somebody outside the crew")

    load = {name: 0 for name in crew}
    worked: dict[str, int] = {}
    nights: list[str] = []

    for night in range(len(weights)):
        chosen = ""
        for name in sorted(crew):
            if name in away[night]:
                continue
            last = worked.get(name)
            if last is not None and night - last <= 2:
                continue
            if chosen == "" or load[name] < load[chosen]:
                chosen = name
        if chosen == "":
            nights.append("?")
            continue
        load[chosen] += weights[night]
        worked[chosen] = night
        nights.append(chosen)
    return nights
