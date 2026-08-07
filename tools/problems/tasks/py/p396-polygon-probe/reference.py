def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _spot(given, what: str) -> list:
    if (
        not isinstance(given, list)
        or len(given) != 2
        or not _whole(given[0])
        or not _whole(given[1])
    ):
        raise ValueError(f"a {what} must be a pair of two whole numbers")
    if abs(given[0]) > 100000 or abs(given[1]) > 100000:
        raise ValueError("a measure magnitude passes one hundred thousand")
    return [given[0], given[1]]


def polygon_probe(outline: list, probes: list) -> dict:
    if not isinstance(outline, list) or not isinstance(probes, list):
        raise ValueError("polygon_probe expects two lists")
    if len(outline) < 3:
        raise ValueError("a ring carries at least three corners")
    ring = [_spot(corner, "corner") for corner in outline]
    for before, after in zip(ring, ring[1:]):
        if before == after:
            raise ValueError("neighbouring corners repeat")
    if ring[0] == ring[-1]:
        raise ValueError("the tail corner equals the opening one")

    sweep = 0
    for index, here in enumerate(ring):
        following = ring[(index + 1) % len(ring)]
        sweep += here[0] * following[1] - following[0] * here[1]
    doubled = abs(sweep)

    marks = []
    for given in probes:
        px, py = _spot(given, "sample spot")
        verdict = ""
        for index, u in enumerate(ring):
            v = ring[(index + 1) % len(ring)]
            side = (v[0] - u[0]) * (py - u[1]) - (v[1] - u[1]) * (px - u[0])
            if (
                side == 0
                and min(u[0], v[0]) <= px <= max(u[0], v[0])
                and min(u[1], v[1]) <= py <= max(u[1], v[1])
            ):
                verdict = "edge"
                break
        if verdict == "":
            held = False
            for index, u in enumerate(ring):
                v = ring[(index + 1) % len(ring)]
                if (u[1] > py) != (v[1] > py):
                    rise = v[1] - u[1]
                    left = (px - u[0]) * rise
                    right = (py - u[1]) * (v[0] - u[0])
                    if (left < right) if rise > 0 else (left > right):
                        held = not held
            verdict = "inside" if held else "outside"
        marks.append(verdict)
    return {"doubled": doubled, "marks": marks}
