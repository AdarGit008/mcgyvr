def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def renewal_thousandths(squads: list) -> list:
    if not isinstance(squads, list):
        raise ValueError("squads must be a list")
    used = set()
    out = []
    for squad in squads:
        if not isinstance(squad, (list, tuple)) or len(squad) != 3:
            raise ValueError("every squad must be a triple")
        name, seats, run = squad[0], squad[1], squad[2]
        if not isinstance(name, str) or name == "":
            raise ValueError("a squad name must be a non-empty string")
        if name in used:
            raise ValueError(f"two squads answer to {name}")
        used.add(name)
        if not _whole(seats) or seats < 1 or seats > 1000000:
            raise ValueError("seats must be a whole number from 1 through 1000000")
        if not isinstance(run, list):
            raise ValueError("a squad's run must be a list")
        strengths = []
        previous = seats
        for tally in run:
            if not _whole(tally) or tally < 0 or tally > seats:
                raise ValueError("a cycle tally must be a whole number within seats")
            if tally > previous:
                raise ValueError("seats are never regained")
            previous = tally
            strengths.append((tally * 2000 + seats) // (2 * seats))
        out.append([name, strengths])
    return out
