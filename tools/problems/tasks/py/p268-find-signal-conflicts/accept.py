from solution import find_signal_conflicts

junction = [
    {"name": "north", "offset": 0, "green": 20, "amber": 4},
    {"name": "south", "offset": 0, "green": 20, "amber": 4},
    {"name": "east", "offset": 26, "green": 20, "amber": 4},
    {"name": "west", "offset": 55, "green": 8, "amber": 2},
]
ring = [
    {"name": "loop", "offset": 18, "green": 4, "amber": 0},
    {"name": "gate", "offset": 15, "green": 5, "amber": 0},
    {"name": "spur", "offset": 2, "green": 2, "amber": 0},
]
tight = [
    {"name": "a", "offset": 0, "green": 10, "amber": 0},
    {"name": "b", "offset": 10, "green": 10, "amber": 0},
    {"name": "c", "offset": 9, "green": 5, "amber": 0},
]

assert find_signal_conflicts(60, junction, []) == [], "no watched pairs, no report"
assert find_signal_conflicts(60, junction, [["north", "east"], ["east", "west"]]) == [], (
    "approaches that never share a second"
)
assert find_signal_conflicts(60, junction, [["north", "south"]]) == ["north~south@0"], (
    "two approaches running the same stage"
)
assert find_signal_conflicts(60, junction, [["west", "north"]]) == ["west~north@0"], (
    "a stage that wraps past the end of the cycle"
)
assert find_signal_conflicts(
    60, junction, [["north", "south"], ["west", "east"], ["west", "south"]]
) == ["north~south@0", "west~south@0"], "two clashes at the same second sort by their text"
assert find_signal_conflicts(20, ring, [["loop", "gate"]]) == ["loop~gate@18"], (
    "the earliest shared second sits before the wrap"
)
assert find_signal_conflicts(20, ring, [["loop", "spur"]]) == [], "a wrapped tail that still clears"
assert find_signal_conflicts(20, tight, [["a", "b"], ["a", "c"], ["b", "c"]]) == ["a~c@9", "b~c@10"], (
    "two clashes reported in second order"
)
assert find_signal_conflicts(20, tight, [["b", "a"], ["c", "a"]]) == ["c~a@9"], (
    "a pair keeps the order it was written in"
)
assert find_signal_conflicts(
    20,
    [{"name": "x", "offset": 0, "green": 20, "amber": 0}, {"name": "y", "offset": 5, "green": 1, "amber": 0}],
    [["x", "y"]],
) == ["x~y@5"], "an approach green for the whole cycle"
assert find_signal_conflicts(20, [{"name": "solo", "offset": 0, "green": 1, "amber": 0}], []) == [], (
    "a single approach with nothing to clash with"
)


def rejects(cycle, approaches, pairs):
    try:
        find_signal_conflicts(cycle, approaches, pairs)
    except ValueError:
        return True
    return False


assert rejects(1.5, ring, []), "a fractional cycle"
assert rejects(1, ring, []), "a cycle under two seconds"
assert rejects(3601, ring, []), "a cycle past the ceiling"
assert rejects(20, [], []), "an empty approach list"
assert rejects(20, "ring", []), "approaches given as text"
assert rejects(20, [{"name": "a", "offset": 0, "green": 5}], []), "an approach missing amber"
assert rejects(20, [{"name": "", "offset": 0, "green": 5, "amber": 0}], []), "an empty approach name"
assert rejects(20, [{"name": "a", "offset": 20, "green": 5, "amber": 0}], []), "an offset equal to the cycle"
assert rejects(20, [{"name": "a", "offset": 0, "green": 0, "amber": 0}], []), "a stage with no green at all"
assert rejects(20, [{"name": "a", "offset": 0, "green": 15, "amber": 6}], []), "green plus amber outrunning the cycle"
assert rejects(
    20,
    [{"name": "a", "offset": 0, "green": 5, "amber": 0}, {"name": "a", "offset": 6, "green": 2, "amber": 0}],
    [],
), "a repeated approach name"
assert rejects(20, ring, [["loop"]]), "a pair naming only one approach"
assert rejects(20, ring, [["loop", "nope"]]), "a pair naming an undeclared approach"
assert rejects(20, ring, [["loop", "loop"]]), "a pair naming one approach twice"
assert rejects(20, ring, [["loop", "gate"], ["gate", "loop"]]), "the same pair listed twice"
assert rejects(20, ring, "pairs"), "pairs given as text"
print("ok")
