def pour_to_target(capacities: list, wanted: int) -> list | None:
    if not isinstance(capacities, list) or not capacities:
        raise ValueError("capacities must be a non-empty list")
    for capacity in capacities:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("every capacity must be a whole number of at least one")
    if not isinstance(wanted, int) or isinstance(wanted, bool) or wanted < 0:
        raise ValueError("wanted must be a whole number of at least zero")

    count = len(capacities)

    def label(index):
        return chr(65 + index)

    def holds(situation):
        return any(amount == wanted for amount in situation)

    start = (0,) * count
    if holds(start):
        return []

    routes = {start: []}
    frontier = [start]
    while frontier:
        next_frontier = []
        for situation in frontier:
            route = routes[situation]
            steps = []
            for i in range(count):
                after = list(situation)
                after[i] = capacities[i]
                steps.append(("fill " + label(i), tuple(after)))
            for i in range(count):
                after = list(situation)
                after[i] = 0
                steps.append(("empty " + label(i), tuple(after)))
            for i in range(count):
                for j in range(count):
                    if i == j:
                        continue
                    room = capacities[j] - situation[j]
                    moved = min(situation[i], room)
                    after = list(situation)
                    after[i] -= moved
                    after[j] += moved
                    steps.append(("pour " + label(i) + " " + label(j), tuple(after)))
            for action, after in steps:
                if after in routes:
                    continue
                extended = route + [action]
                if holds(after):
                    return extended
                routes[after] = extended
                next_frontier.append(after)
        frontier = next_frontier
    return None
