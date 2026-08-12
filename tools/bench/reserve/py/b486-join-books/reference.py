def join_books(first: dict[str, int], second: dict[str, int]) -> dict[str, int]:
    joined = {}
    for name in first:
        joined[name] = first[name]
    for name in second:
        if name in joined and joined[name] != second[name]:
            raise ValueError("the two books disagree on " + name)
        joined[name] = second[name]
    return joined
