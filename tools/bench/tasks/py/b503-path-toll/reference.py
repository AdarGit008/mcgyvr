def step_cost(kind: str) -> int:
    if kind == "hill":
        return 5
    if kind == "flat":
        return 2
    return 3


def path_toll(steps: list[str]) -> int:
    """The path totalled, with every third step free."""
    total = 0
    for i in range(len(steps)):
        if (i + 1) % 3 != 0:
            total += step_cost(steps[i])
    return total
