"""Resolve a dispatcher's typed fragment against the station names on file."""


def match_station(names, fragment):
    if fragment == "":
        raise ValueError("the fragment must not be empty")
    needle = fragment.lower()
    best = None
    best_rank = None
    for name in names:
        plain = name.lower()
        if plain == needle:
            kind = 1
        elif plain.startswith(needle):
            kind = 2
        elif needle in plain:
            kind = 3
        else:
            continue
        rank = (kind, len(plain), plain)
        if best_rank is None or rank < best_rank:
            best, best_rank = name, rank
    return best
