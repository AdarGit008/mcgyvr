def replay_tessel_match(rallies: list[str]) -> dict:
    if not isinstance(rallies, list):
        raise ValueError("replay_tessel_match expects a list of rally winners")
    bands = {"A": 0, "B": 0}
    points = {"A": 0, "B": 0}
    serve = "A"
    winner = ""
    for rally in rallies:
        if rally not in ("A", "B"):
            raise ValueError("a rally winner is either A or B")
        if winner:
            raise ValueError("the match is already decided")
        other = "B" if rally == "A" else "A"
        if rally != serve:
            serve = rally
            continue
        points[rally] += 1
        mine = points[rally]
        theirs = points[other]
        if (mine >= 7 and mine - theirs >= 2) or mine >= 10:
            bands[rally] += 1
            if bands[rally] == 3:
                winner = rally
                serve = ""
            else:
                points = {"A": 0, "B": 0}
                serve = other
    return {
        "winner": winner,
        "bands": [bands["A"], bands["B"]],
        "points": [points["A"], points["B"]],
        "serve": serve,
    }
