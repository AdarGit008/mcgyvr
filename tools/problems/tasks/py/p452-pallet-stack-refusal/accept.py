from solution import stack_pallet


def carton(name, mass, bears, high, wide, top):
    return {"name": name, "mass": mass, "bears": bears, "high": high, "wide": wide, "top": top}


roomy = {"deck": 200, "roof": 100}

assert stack_pallet(
    [carton("base", 40, 100, 20, 12, False), carton("mid", 30, 50, 15, 10, False), carton("cap", 10, 0, 5, 8, True)],
    roomy,
) == {"stacked": ["base", "mid", "cap"], "refused": "", "reason": "", "mass": 80, "high": 40}, (
    "a lawful column of three goes up whole"
)
assert stack_pallet(
    [carton("base", 40, 100, 20, 12, False), carton("cap", 10, 0, 5, 8, True), carton("extra", 5, 0, 3, 6, False)],
    roomy,
) == {"stacked": ["base", "cap"], "refused": "extra", "reason": "capped", "mass": 50, "high": 25}, (
    "nothing may ride on a carton flagged top"
)
assert stack_pallet([carton("base", 40, 100, 20, 10, False), carton("wide", 5, 10, 4, 11, False)], roomy) == {
    "stacked": ["base"],
    "refused": "wide",
    "reason": "overhang",
    "mass": 40,
    "high": 20,
}, "a broader carton may not sit on a narrower one"
assert stack_pallet([carton("base", 40, 20, 20, 12, False), carton("mid", 30, 50, 15, 10, False)], roomy) == {
    "stacked": ["base"],
    "refused": "mid",
    "reason": "crush",
    "mass": 40,
    "high": 20,
}, "the carton directly beneath refuses the load"
assert stack_pallet(
    [carton("base", 40, 45, 20, 12, False), carton("mid", 30, 80, 15, 10, False), carton("top", 20, 0, 5, 8, False)],
    {"deck": 500, "roof": 500},
) == {"stacked": ["base", "mid"], "refused": "top", "reason": "crush", "mass": 70, "high": 35}, (
    "a carton two rungs down is crushed although its neighbour is not"
)
assert stack_pallet(
    [carton("base", 40, 100, 20, 12, False), carton("mid", 30, 50, 15, 10, False)], {"deck": 60, "roof": 100}
) == {"stacked": ["base"], "refused": "mid", "reason": "deck", "mass": 40, "high": 20}, (
    "the deck rating stops the column"
)
assert stack_pallet(
    [carton("base", 40, 100, 20, 12, False), carton("mid", 30, 50, 15, 10, False)], {"deck": 200, "roof": 30}
) == {"stacked": ["base"], "refused": "mid", "reason": "roof", "mass": 40, "high": 20}, (
    "the doorway rating stops the column"
)
assert stack_pallet([], {"deck": 10, "roof": 10}) == {
    "stacked": [],
    "refused": "",
    "reason": "",
    "mass": 0,
    "high": 0,
}, "no cartons at all leaves a bare pallet"
assert stack_pallet(
    [carton("base", 1, 100, 1, 4, False), carton("bad", 99, 0, 1, 9, False)], {"deck": 10, "roof": 10}
) == {"stacked": ["base"], "refused": "bad", "reason": "overhang", "mass": 1, "high": 1}, (
    "overhang is named ahead of the deck rating"
)
assert stack_pallet(
    [carton("base", 1, 2, 1, 4, False), carton("bad", 99, 0, 1, 4, False)], {"deck": 10, "roof": 10}
) == {"stacked": ["base"], "refused": "bad", "reason": "crush", "mass": 1, "high": 1}, (
    "crushing is named ahead of the deck rating"
)
assert stack_pallet(
    [carton("base", 9, 100, 9, 4, False), carton("bad", 9, 0, 9, 4, False)], {"deck": 10, "roof": 10}
) == {"stacked": ["base"], "refused": "bad", "reason": "deck", "mass": 9, "high": 9}, (
    "the deck rating is named ahead of the doorway"
)
assert stack_pallet([carton("only", 7, 0, 3, 5, False)], {"deck": 10, "roof": 10}) == {
    "stacked": ["only"],
    "refused": "",
    "reason": "",
    "mass": 7,
    "high": 3,
}, "a carton that bears nothing is fine with nothing on it"
assert stack_pallet(
    [carton("a", 5, 5, 5, 5, False), carton("b", 5, 0, 5, 5, False)], {"deck": 10, "roof": 10}
) == {"stacked": ["a", "b"], "refused": "", "reason": "", "mass": 10, "high": 10}, (
    "sitting exactly on every rating is allowed"
)


def rejects(items, limits):
    try:
        stack_pallet(items, limits)
    except ValueError:
        return True
    return False


assert rejects("nope", roomy), "items that are not a list are refused"
assert rejects([carton("a", 1, 1, 1, 1, False)], None), "limits that are not a record are refused"
assert rejects([], {"deck": 0, "roof": 10}), "a deck rating of nought is refused"
assert rejects([], {"roof": 10}), "a missing deck rating is refused"
assert rejects([], {"deck": 10, "roof": 1.5}), "a fractional doorway rating is refused"
assert rejects([["a"]], roomy), "an item that is not a record is refused"
assert rejects([carton("", 1, 1, 1, 1, False)], roomy), "an empty name is refused"
assert rejects(
    [carton("a", 1, 1, 1, 1, False), carton("a", 2, 1, 1, 1, False)], roomy
), "two cartons answering to one name are refused"
assert rejects([carton("a", 0, 1, 1, 1, False)], roomy), "a mass of nought is refused"
assert rejects([carton("a", 1, -1, 1, 1, False)], roomy), "a negative bearing is refused"
assert rejects([carton("a", 1, 1, 0, 1, False)], roomy), "a height of nought is refused"
assert rejects([carton("a", 1, 1, 1, 1.5, False)], roomy), "a fractional width is refused"
assert rejects([carton("a", 1, 1, 1, 1, "yes")], roomy), "a top flag that is not a boolean is refused"
print("ok")
