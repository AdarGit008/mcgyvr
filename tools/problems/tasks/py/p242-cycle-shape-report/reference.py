from math import gcd


def cycle_shape_report(chart: list[int]) -> dict:
    if not isinstance(chart, list) or not chart:
        raise ValueError("the chart must be a non-empty list")
    seats = len(chart)
    named = set()
    for entry in chart:
        if not isinstance(entry, int) or isinstance(entry, bool):
            raise ValueError("every entry must be a whole number")
        if entry < 0 or entry >= seats:
            raise ValueError("entry names a seat outside the chart")
        if entry in named:
            raise ValueError("two entries name the same seat")
        named.add(entry)
    traced = [False] * seats
    loops = []
    for start in range(seats):
        if traced[start]:
            continue
        loop = []
        at = start
        while not traced[at]:
            traced[at] = True
            loop.append(at)
            at = chart[at]
        loops.append(loop)
    widths = sorted((len(loop) for loop in loops), reverse=True)
    repeat = 1
    for width in widths:
        repeat = repeat // gcd(repeat, width) * width
    swing = "even" if (seats - len(loops)) % 2 == 0 else "odd"
    return {"loops": loops, "widths": widths, "repeat": repeat, "swing": swing}
