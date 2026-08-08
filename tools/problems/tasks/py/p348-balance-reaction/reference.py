import re

SPECIES = re.compile(r"^([A-Z][a-z]?\d*)+$")
GROUP = re.compile(r"([A-Z][a-z]?)(\d*)")
TOP = 12
ROOM = 5


def _read_species(species: str) -> dict[str, int]:
    if SPECIES.match(species) is None:
        raise ValueError("a species must be a run of groups")
    counts: dict[str, int] = {}
    for symbol, digits in GROUP.findall(species):
        count = 1
        if digits != "":
            if digits[0] == "0":
                raise ValueError("a count may not carry a leading zero")
            count = int(digits)
            if count < 2:
                raise ValueError("a count must be two or more")
        counts[symbol] = counts.get(symbol, 0) + count
    return counts


def _read_side(side: str) -> list[str]:
    if side.strip() == "":
        raise ValueError("a side must list at least one species")
    parts = side.split(" + ")
    if len(set(parts)) != len(parts):
        raise ValueError("a species may not be listed twice on one side")
    return parts


def balance_reaction(equation: str) -> str:
    if not isinstance(equation, str):
        raise ValueError("the reaction must be a string")
    sides = equation.split(" -> ")
    if len(sides) != 2:
        raise ValueError("the reaction must carry exactly one arrow")
    left = _read_side(sides[0])
    right = _read_side(sides[1])
    names = left + right
    if len(names) > ROOM:
        raise ValueError("a reaction may name at most five species")
    tables = [_read_species(name) for name in names]

    symbols: list[str] = []
    for table in tables:
        for symbol in table:
            if symbol not in symbols:
                symbols.append(symbol)
    width = len(symbols)
    vectors = [
        [table.get(symbol, 0) * (1 if index < len(left) else -1) for symbol in symbols]
        for index, table in enumerate(tables)
    ]

    size = len(names)
    totals = [0] * width
    choice = [0] * size
    best: list[int] | None = None
    best_sum = 10**9

    def walk(index: int, total: int) -> None:
        nonlocal best, best_sum
        if total + (size - index) >= best_sum:
            return
        if index == size:
            if all(value == 0 for value in totals):
                best_sum = total
                best = list(choice)
            return
        for take in range(1, TOP + 1):
            choice[index] = take
            for e in range(width):
                totals[e] += vectors[index][e] * take
            walk(index + 1, total + take)
            for e in range(width):
                totals[e] -= vectors[index][e] * take

    walk(0, 0)
    if best is None:
        return ""
    picked = best

    def render(start: int, listing: list[str]) -> str:
        return " + ".join(
            name if picked[start + i] == 1 else f"{picked[start + i]} {name}"
            for i, name in enumerate(listing)
        )

    return f"{render(0, left)} -> {render(len(left), right)}"
