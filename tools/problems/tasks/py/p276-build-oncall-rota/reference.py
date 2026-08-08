def build_on_call_rota(roster: list[str], blocked: list[list[str]]) -> list[str]:
    if not isinstance(roster, list) or not roster:
        raise ValueError("the roster must hold at least one person")
    seen: set[str] = set()
    for name in roster:
        if not isinstance(name, str) or not name:
            raise ValueError("a roster name must be a non-empty string")
        if name in seen:
            raise ValueError("the roster repeats a name")
        seen.add(name)
    if not isinstance(blocked, list) or not blocked:
        raise ValueError("there must be at least one shift")

    bans: list[set[str]] = []
    for entry in blocked:
        if not isinstance(entry, list):
            raise ValueError("a shift's blocked entry must be a list")
        ban: set[str] = set()
        for name in entry:
            if not isinstance(name, str) or name not in seen:
                raise ValueError("a blocked name is not on the roster")
            if name in ban:
                raise ValueError("a name is blocked twice in one shift")
            ban.add(name)
        bans.append(ban)

    shifts = len(bans)
    ceiling = -(-shifts // len(roster))
    tally = {name: 0 for name in roster}
    rota: list[str] = []
    previous = ""

    for shift in range(shifts):
        chosen = ""
        for name in roster:
            if name in bans[shift] or name == previous:
                continue
            if tally[name] >= ceiling:
                continue
            if chosen == "" or tally[name] < tally[chosen]:
                chosen = name
        if chosen == "":
            return []
        tally[chosen] += 1
        rota.append(chosen)
        previous = chosen
    return rota
