def run_bye_ladder(seeds: list[str], upsets: list[str]) -> dict:
    if not isinstance(seeds, list) or not isinstance(upsets, list):
        raise ValueError("run_bye_ladder expects two lists")
    if len(seeds) < 2:
        raise ValueError("a ladder needs at least two entrants")
    rank: dict[str, int] = {}
    for name in seeds:
        if not isinstance(name, str):
            raise ValueError("an entrant name is a string")
        if name in rank:
            raise ValueError(f"entered twice: {name}")
        rank[name] = len(rank)
    beats: set[str] = set()
    for name in upsets:
        if not isinstance(name, str) or name not in rank:
            raise ValueError(f"upset names no entrant: {name}")
        if name in beats:
            raise ValueError(f"upset named twice: {name}")
        beats.add(name)

    sat: set[str] = set()
    rounds: list[dict] = []
    alive = list(seeds)
    while len(alive) > 1:
        bye = None
        playing = alive
        if len(alive) % 2 == 1:
            bye = alive[0]
            for name in alive:
                if name not in sat:
                    bye = name
                    break
            sat.add(bye)
            playing = [name for name in alive if name != bye]
        matches: list[list[str]] = []
        winners: list[str] = []
        for at in range(len(playing) // 2):
            stronger = playing[at]
            weaker = playing[len(playing) - 1 - at]
            matches.append([stronger, weaker])
            winners.append(weaker if weaker in beats else stronger)
        if bye is not None:
            winners.append(bye)
        winners.sort(key=lambda name: rank[name])
        alive = winners
        rounds.append({"bye": bye, "matches": matches})
    return {"rounds": rounds, "champion": alive[0]}
