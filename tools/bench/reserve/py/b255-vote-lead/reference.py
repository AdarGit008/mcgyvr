def vote_lead(ballots: list) -> str:
    if not ballots:
        raise ValueError("no ballots cast")
    tally = {}
    for name in ballots:
        tally[name] = tally.get(name, 0) + 1
    best = sorted(tally)[0]
    for name in sorted(tally):
        if tally[name] > tally[best]:
            best = name
    return best
