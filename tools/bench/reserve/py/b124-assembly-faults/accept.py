from solution import run_assembly

assert run_assembly(
    {"bolt": 6, "panel": 2, "gear": 1},
    [["frame", {"bolt": 2, "panel": 1}, False], ["door", {"panel": 1, "bolt": 1}, False]],
) == {
    "built": ["frame", "door"],
    "faults": [],
    "halted": None,
    "leftover": [["bolt", 3], ["gear", 1], ["panel", 0]],
}, "a clean run builds every step"
assert run_assembly(
    {"bolt": 3, "panel": 1},
    [["frame", {"bolt": 2, "panel": 2}, False], ["lid", {"bolt": 3}, False]],
) == {
    "built": ["lid"],
    "faults": [["frame", "panel"]],
    "halted": None,
    "leftover": [["bolt", 0], ["panel", 1]],
}, "a faulted step consumes nothing, so later steps still draw stock"
assert run_assembly(
    {"cell": 2},
    [["pack", {"cell": 3}, True], ["trim", {}, False]],
) == {
    "built": [],
    "faults": [["pack", "cell"]],
    "halted": "pack",
    "leftover": [["cell", 2]],
}, "a critical fault halts before later steps run"
assert run_assembly(
    {"axle": 1, "bolt": 0, "arm": 0},
    [["cart", {"bolt": 2, "arm": 1, "axle": 1}, False]],
) == {
    "built": [],
    "faults": [["cart", "arm"]],
    "halted": None,
    "leftover": [["arm", 0], ["axle", 1], ["bolt", 0]],
}, "the fault names the alphabetically first short part"
assert run_assembly({}, [["poll", {}, False]]) == {
    "built": ["poll"],
    "faults": [],
    "halted": None,
    "leftover": [],
}, "a step needing nothing always builds"
assert run_assembly({"nut": 4}, []) == {
    "built": [],
    "faults": [],
    "halted": None,
    "leftover": [["nut", 4]],
}, "an empty plan leaves the bins alone"
assert run_assembly(
    {"rod": 4},
    [["a1", {"rod": 2}, False], ["a2", {"rod": 2}, False], ["a3", {"rod": 1}, False]],
) == {
    "built": ["a1", "a2"],
    "faults": [["a3", "rod"]],
    "halted": None,
    "leftover": [["rod", 0]],
}, "stock drains to exactly zero, then the next draw faults"
assert run_assembly(
    {"pin": 2},
    [["core", {"pin": 1}, True], ["rim", {"pin": 1}, False]],
) == {
    "built": ["core", "rim"],
    "faults": [],
    "halted": None,
    "leftover": [["pin", 0]],
}, "a critical step that succeeds does not halt"
assert run_assembly(
    {"cap": 1},
    [["c1", {"cap": 2}, False], ["c2", {"cap": 3}, False]],
) == {
    "built": [],
    "faults": [["c1", "cap"], ["c2", "cap"]],
    "halted": None,
    "leftover": [["cap", 1]],
}, "non-critical faults accumulate in order"


def rejects(*args):
    try:
        run_assembly(*args)
    except ValueError:
        return True
    return False


assert rejects({"bolt": -1}, []), "negative stock"
assert rejects({"": 2}, []), "empty bin name"
assert rejects({"bolt": 1}, [["s", {"bolt": 1}]]), "two-item step"
assert rejects({"bolt": 1}, [["", {"bolt": 1}, False]]), "empty step name"
assert rejects({"bolt": 1}, [["s", {"screw": 1}, False]]), "unknown part"
assert rejects({"bolt": 1}, [["s", {"bolt": 0}, False]]), "zero needed count"
assert rejects({"bolt": 1}, [["s", {"bolt": 1}, "yes"]]), "non-boolean critical flag"
print("ok")
