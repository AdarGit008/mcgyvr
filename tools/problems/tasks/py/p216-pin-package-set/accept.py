from solution import pin_package_set


def want(name, low, high):
    return {"name": name, "from": low, "under": high}


def plan(shelf, needs, root):
    return {"shelf": shelf, "needs": needs, "root": root}


def pin(name, version):
    return {"name": name, "version": version}


def rejects(value):
    try:
        pin_package_set(value)
    except ValueError:
        return True
    return False


assert pin_package_set(plan({"g": ["1.0.0"]}, {}, [])) == {
    "picked": [],
    "stuck": [],
}, "an application that asks for nothing settles nothing"
assert pin_package_set(
    plan({"a": ["1.0.0", "1.2.0", "2.0.0"]}, {}, [want("a", "1.0.0", "3.0.0")])
) == {
    "picked": [pin("a", "1.2.0")],
    "stuck": [],
}, "the oldest generation still allowed, at its freshest build"
assert pin_package_set(
    plan({"h": ["1.2.0", "1.2.7", "1.2.3"]}, {}, [want("h", "1.0.0", "2.0.0")])
) == {
    "picked": [pin("h", "1.2.7")],
    "stuck": [],
}, "the third group breaks a tie on the first two"
assert pin_package_set(
    plan(
        {"a": ["1.0.0"], "b": ["2.0.0", "2.1.0"]},
        {"a": [want("b", "2.0.0", "3.0.0")]},
        [want("a", "1.0.0", "2.0.0")],
    )
) == {
    "picked": [pin("a", "1.0.0"), pin("b", "2.1.0")],
    "stuck": [],
}, "a settled package drags its own wants in"
assert pin_package_set(
    plan(
        {"a": ["1.0.0"], "b": ["1.0.0", "1.5.0", "2.0.0"]},
        {"a": [want("b", "1.5.0", "3.0.0")]},
        [want("a", "1.0.0", "2.0.0"), want("b", "1.0.0", "2.0.0")],
    )
) == {
    "picked": [pin("a", "1.0.0"), pin("b", "1.5.0")],
    "stuck": [],
}, "two windows on one package must both hold"
assert pin_package_set(
    plan(
        {"g": ["1.0.0", "2.0.0", "2.3.0"]},
        {},
        [want("g", "1.0.0", "3.0.0"), want("g", "2.0.0", "3.0.0")],
    )
) == {
    "picked": [pin("g", "2.3.0")],
    "stuck": [],
}, "a floor from one want lifts the whole choice"
assert pin_package_set(
    plan({"c": ["1.0.0"]}, {}, [want("c", "2.0.0", "3.0.0")])
) == {
    "picked": [],
    "stuck": ["c"],
}, "a window nothing on the shelf satisfies is stuck"
assert pin_package_set(
    plan(
        {"d": ["1.0.0"], "e": ["1.0.0"]},
        {"d": [want("e", "1.0.0", "2.0.0")]},
        [want("d", "5.0.0", "6.0.0")],
    )
) == {
    "picked": [pin("e", "1.0.0")],
    "stuck": ["d"],
}, "a stuck package still drags its wants in"
assert pin_package_set(
    plan(
        {"a": ["1.0.0"], "b": ["1.0.0"]},
        {"a": [want("b", "1.0.0", "2.0.0")], "b": [want("a", "1.0.0", "2.0.0")]},
        [want("a", "1.0.0", "2.0.0")],
    )
) == {
    "picked": [pin("a", "1.0.0"), pin("b", "1.0.0")],
    "stuck": [],
}, "wants that point at each other still finish"
assert pin_package_set(
    plan({"k": ["9.0.0", "10.1.0"]}, {}, [want("k", "1.0.0", "11.0.0")])
) == {
    "picked": [pin("k", "9.0.0")],
    "stuck": [],
}, "groups compare as numbers, not as text"

assert rejects([1, 2]), "a plan that is not a mapping is rejected"
assert rejects({"shelf": [], "needs": {}, "root": []}), "a shelf that is not a mapping"
assert rejects(
    {"shelf": {"a": ["1.0.0"]}, "needs": [], "root": []}
), "needs that is not a mapping is rejected"
assert rejects(
    {"shelf": {"a": ["1.0.0"]}, "needs": {}, "root": {}}
), "a root that is not a list is rejected"
assert rejects(plan({"a": []}, {}, [])), "an empty shelf entry is rejected"
assert rejects(plan({"a": ["1.2"]}, {}, [])), "a version of two groups is rejected"
assert rejects(plan({"a": ["01.2.0"]}, {}, [])), "a leading zero is rejected"
assert rejects(plan({"a": ["1.0.0", "1.0.0"]}, {}, [])), "a repeated version"
assert rejects(plan({"a": ["1.0.0"]}, {"z": []}, [])), "needs keyed by an unstocked package"
assert rejects(plan({"a": ["1.0.0"]}, {}, ["a"])), "a want that is not a mapping"
assert rejects(
    plan({"a": ["1.0.0"]}, {}, [want("zz", "1.0.0", "2.0.0")])
), "a want on an unstocked package is rejected"
assert rejects(
    plan({"a": ["1.0.0"]}, {}, [want("a", "2.0.0", "1.0.0")])
), "a window that runs backwards is rejected"
assert rejects(
    plan({"a": ["1.0.0"]}, {}, [want("a", "1.0.0", "1.0.0")])
), "an empty window is rejected"

print("ok")
