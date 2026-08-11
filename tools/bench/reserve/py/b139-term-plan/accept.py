from solution import plan_terms

assert plan_terms([], [], 3) == [], "no courses, no terms"
assert plan_terms(["welding"], [], 2) == [["welding"]], "a lone course"
assert plan_terms(["forging", "casting", "milling"], [], 2) == [
    ["casting", "forging"],
    ["milling"],
], "independent courses fill terms to capacity"
assert plan_terms(["ore", "ingot", "blade"], [["ingot", "ore"], ["blade", "ingot"]], 3) == [
    ["ore"],
    ["ingot"],
    ["blade"],
], "a chain stretches over terms despite room"
assert plan_terms(["saw", "wood"], [["saw", "wood"]], 2) == [
    ["wood"],
    ["saw"],
], "a prerequisite never shares its course's term"
assert plan_terms(
    ["base", "left", "right", "top"],
    [["left", "base"], ["right", "base"], ["top", "left"], ["top", "right"]],
    2,
) == [["base"], ["left", "right"], ["top"]], "a diamond of prerequisites"
assert plan_terms(["zinc", "alloy", "brass"], [], 2) == [
    ["alloy", "brass"],
    ["zinc"],
], "capacity defers the alphabetically last"
assert plan_terms(["cut", "polish", "zebra"], [["polish", "cut"]], 1) == [
    ["cut"],
    ["polish"],
    ["zebra"],
], "a deferred course competes alphabetically with the newly unlocked"


def rejects(*args):
    try:
        plan_terms(*args)
    except Exception:
        return True
    return False


assert rejects("welding", [], 1), "non-list courses rejected"
assert rejects([""], [], 1), "empty course name rejected"
assert rejects([7], [], 1), "non-string course rejected"
assert rejects(["kiln", "kiln"], [], 1), "duplicate course rejected"
assert rejects(["kiln"], [["kiln"]], 1), "one-item prereq rejected"
assert rejects(["kiln"], [["kiln", "glaze"]], 1), "unknown course rejected"
assert rejects(["kiln"], [], 0), "zero capacity rejected"
assert rejects(["kiln"], [], 1.5), "fractional capacity rejected"
assert rejects(
    ["kiln", "glaze"], [["kiln", "glaze"], ["glaze", "kiln"]], 1
), "a prerequisite cycle is rejected"
assert rejects(["kiln"], [["kiln", "kiln"]], 1), "self-prerequisite rejected"
print("ok")
