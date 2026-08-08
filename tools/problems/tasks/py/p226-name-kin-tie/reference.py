ORDINAL = [
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
]

REMOVAL = [
    "once removed",
    "twice removed",
    "three times removed",
    "four times removed",
    "five times removed",
    "six times removed",
    "seven times removed",
    "eight times removed",
    "nine times removed",
    "ten times removed",
]


def _reach(parents: dict, start: str) -> dict:
    seen = {start: 0}
    frontier = [start]
    step = 0
    while frontier:
        step += 1
        following = []
        for node in frontier:
            for up in parents.get(node, ()):
                if up == start:
                    raise ValueError("the links close a loop")
                if up not in seen:
                    seen[up] = step
                    following.append(up)
        frontier = following
    return seen


def _greats(count: int, base: str) -> str:
    return "great-" * count + base


def name_kin_tie(links: list, one: str, other: str) -> str:
    if not isinstance(links, list):
        raise ValueError("the links must be a list")
    parents = {}
    people = set()
    pairs = set()
    for link in links:
        if not isinstance(link, dict):
            raise ValueError("a link must be a mapping")
        child = link.get("child")
        parent = link.get("parent")
        if not isinstance(child, str) or not child:
            raise ValueError("a child must be a non-empty name")
        if not isinstance(parent, str) or not parent:
            raise ValueError("a parent must be a non-empty name")
        if child == parent:
            raise ValueError("nobody is their own parent")
        if (child, parent) in pairs:
            raise ValueError("a link is listed twice")
        pairs.add((child, parent))
        held = parents.setdefault(child, [])
        if len(held) == 2:
            raise ValueError("nobody has a third parent")
        held.append(parent)
        people.add(child)
        people.add(parent)
    for person in sorted(people):
        _reach(parents, person)
    if not isinstance(one, str) or one not in people:
        raise ValueError("the second person is named nowhere in the links")
    if not isinstance(other, str) or other not in people:
        raise ValueError("the third person is named nowhere in the links")

    mine = _reach(parents, one)
    theirs = _reach(parents, other)
    best = None
    for forebear, up in mine.items():
        down = theirs.get(forebear)
        if down is None:
            continue
        key = (max(up, down), min(up, down))
        if best is None or key < best[0]:
            best = (key, up, down)
    if best is None:
        return "unrelated"
    _, u, v = best
    if u == 0 and v == 0:
        return "self"
    if v == 0:
        return "parent" if u == 1 else _greats(u - 2, "grandparent")
    if u == 0:
        return "child" if v == 1 else _greats(v - 2, "grandchild")
    if u == 1 and v == 1:
        return "sibling"
    if v == 1:
        return _greats(u - 2, "aunt-or-uncle")
    if u == 1:
        return _greats(v - 2, "niece-or-nephew")
    degree = min(u, v) - 1
    removal = abs(u - v)
    if degree > len(ORDINAL):
        raise ValueError("the cousin degree runs past ten")
    if removal > len(REMOVAL):
        raise ValueError("the removal runs past ten")
    named = ORDINAL[degree - 1] + " cousin"
    return named if removal == 0 else named + " " + REMOVAL[removal - 1]
