def whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def find_signal_conflicts(cycle: int, approaches: list, pairs: list) -> list:
    if not whole(cycle) or cycle < 2 or cycle > 3600:
        raise ValueError("cycle must be a whole number of seconds in 2..3600")
    if not isinstance(approaches, list) or not approaches:
        raise ValueError("approaches must be a non-empty list")
    lit = {}
    for approach in approaches:
        if not isinstance(approach, dict):
            raise ValueError("each approach must be a record")
        if sorted(approach) != ["amber", "green", "name", "offset"]:
            raise ValueError("each approach carries exactly name, offset, green, amber")
        name = approach["name"]
        if not isinstance(name, str) or name == "":
            raise ValueError("an approach name must be non-empty text")
        offset = approach["offset"]
        green = approach["green"]
        amber = approach["amber"]
        if not whole(offset) or not whole(green) or not whole(amber):
            raise ValueError("offset, green and amber must be whole numbers")
        if offset < 0 or offset >= cycle:
            raise ValueError("offset must lie in 0..cycle-1")
        if green < 1 or amber < 0:
            raise ValueError("green must be at least one second and amber at least none")
        if green + amber > cycle:
            raise ValueError("green plus amber must not outrun the cycle")
        if name in lit:
            raise ValueError("approach names must not repeat")
        marks = [False] * cycle
        for step in range(green + amber):
            marks[(offset + step) % cycle] = True
        lit[name] = marks

    if not isinstance(pairs, list):
        raise ValueError("pairs must be a list")
    already = set()
    found = []
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("each pair names exactly two approaches")
        one, two = pair
        if not isinstance(one, str) or not isinstance(two, str):
            raise ValueError("a pair names approaches by text")
        if one not in lit or two not in lit:
            raise ValueError("a pair names an approach that was never declared")
        if one == two:
            raise ValueError("a pair must name two different approaches")
        key = (one, two) if one < two else (two, one)
        if key in already:
            raise ValueError("the same pair is listed twice")
        already.add(key)
        left = lit[one]
        right = lit[two]
        for second in range(cycle):
            if left[second] and right[second]:
                found.append((second, one + "~" + two + "@" + str(second)))
                break
    found.sort()
    return [text for _, text in found]
