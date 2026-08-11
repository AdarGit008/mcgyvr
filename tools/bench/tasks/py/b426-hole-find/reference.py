def steps_on(first: int, count: int) -> list:
    return [first + i for i in range(count)]


def hole_find(seen: list, first: int, count: int) -> int:
    for wanted in steps_on(first, count):
        if wanted not in seen:
            return wanted
    return 0
