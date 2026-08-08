import re

SYMBOL = re.compile(r"^[A-Z][a-z]?$")
TOP = 10
ROOM = 5


def _check_side(side: object, label: str) -> list[dict[str, int]]:
    if not isinstance(side, list):
        raise ValueError(f"the {label} side must be a list")
    if len(side) == 0:
        raise ValueError(f"the {label} side must name at least one species")
    for species in side:
        if not isinstance(species, dict):
            raise ValueError("a species must be a plain mapping")
        if len(species) == 0:
            raise ValueError("a species must mention at least one symbol")
        for symbol, held in species.items():
            if not isinstance(symbol, str) or SYMBOL.match(symbol) is None:
                raise ValueError(
                    "a symbol is one capital letter and at most one small one"
                )
            if isinstance(held, bool) or not isinstance(held, int) or held < 1:
                raise ValueError("a holding must be a whole number of one or more")
    return side


def settle_reaction_counts(
    left: list[dict[str, int]], right: list[dict[str, int]]
) -> list[int]:
    left_side = _check_side(left, "left-hand")
    right_side = _check_side(right, "right-hand")
    names = left_side + right_side
    if len(names) > ROOM:
        raise ValueError("the two sides may name at most five species between them")

    symbols: list[str] = []
    for species in names:
        for symbol in species:
            if symbol not in symbols:
                symbols.append(symbol)
    width = len(symbols)
    vectors = [
        [
            species.get(symbol, 0) * (1 if index < len(left_side) else -1)
            for symbol in symbols
        ]
        for index, species in enumerate(names)
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
    return [] if best is None else best
