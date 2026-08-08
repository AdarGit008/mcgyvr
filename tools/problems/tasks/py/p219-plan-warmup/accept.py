from solution import plan_warmup


def brief(budget, slots, caps, items):
    return {"budget": budget, "slots": slots, "caps": caps, "items": items}


def item(name, size, weight, family):
    return {"name": name, "bytes": size, "weight": weight, "family": family}


def away(name, why):
    return {"name": name, "why": why}


def rejects(value):
    try:
        plan_warmup(value)
    except ValueError:
        return True
    return False


assert plan_warmup(brief(10, 3, {}, [])) == {
    "loaded": [],
    "spare": 10,
    "turned": [],
}, "nothing offered, nothing loaded"
assert plan_warmup(
    brief(100, 5, {"g": 5}, [item("a", 10, 5, "g"), item("b", 20, 3, "g")])
) == {
    "loaded": ["a", "b"],
    "spare": 70,
    "turned": [],
}, "everything fits and the heavier goes first"
assert plan_warmup(
    brief(100, 1, {"g": 5}, [item("a", 10, 5, "g"), item("b", 20, 3, "g")])
) == {
    "loaded": ["a"],
    "spare": 90,
    "turned": [away("b", "slots")],
}, "the store runs out of places"
assert plan_warmup(
    brief(
        100,
        5,
        {"g": 1, "h": 2},
        [item("a", 10, 5, "g"), item("b", 20, 3, "g"), item("c", 5, 1, "h")],
    )
) == {
    "loaded": ["a", "c"],
    "spare": 85,
    "turned": [away("b", "family")],
}, "a family stops contributing once its cap is spent"
assert plan_warmup(
    brief(
        12,
        5,
        {"g": 5},
        [item("a", 10, 9, "g"), item("b", 5, 8, "g"), item("c", 2, 7, "g")],
    )
) == {
    "loaded": ["a", "c"],
    "spare": 0,
    "turned": [away("b", "bytes")],
}, "the walk goes on past an item the budget cannot hold"
assert plan_warmup(
    brief(3, 1, {"g": 5}, [item("a", 3, 9, "g"), item("b", 50, 8, "g")])
) == {
    "loaded": ["a"],
    "spare": 0,
    "turned": [away("b", "slots")],
}, "no place left is judged before the budget"
assert plan_warmup(
    brief(5, 5, {"g": 1}, [item("a", 5, 9, "g"), item("b", 50, 8, "g")])
) == {
    "loaded": ["a"],
    "spare": 0,
    "turned": [away("b", "family")],
}, "a spent family is judged before the budget"
assert plan_warmup(
    brief(
        100,
        5,
        {"g": 9},
        [item("zed", 4, 2, "g"), item("abe", 4, 2, "g"), item("mid", 1, 2, "g")],
    )
) == {
    "loaded": ["mid", "abe", "zed"],
    "spare": 91,
    "turned": [],
}, "equal weight settles on bytes then on the name"
assert plan_warmup(brief(100, 5, {"g": 0}, [item("a", 1, 1, "g")])) == {
    "loaded": [],
    "spare": 100,
    "turned": [away("a", "family")],
}, "a cap of nothing keeps the whole family out"
assert plan_warmup(
    brief(
        6,
        2,
        {"g": 2, "h": 2},
        [
            item("w", 5, 4, "g"),
            item("x", 4, 3, "h"),
            item("y", 1, 2, "g"),
            item("z", 1, 1, "h"),
        ],
    )
) == {
    "loaded": ["w", "y"],
    "spare": 0,
    "turned": [away("x", "bytes"), away("z", "slots")],
}, "three limits bite in one walk"

assert rejects([1, 2]), "a brief that is not a mapping is rejected"
assert rejects(brief(-1, 1, {}, [])), "a negative budget is rejected"
assert rejects(brief(10, 0, {}, [])), "a store with no places is rejected"
assert rejects(brief(10, 1, [], [])), "caps that is not a mapping is rejected"
assert rejects(brief(10, 1, {}, "none")), "items that is not a list is rejected"
assert rejects(brief(10, 1, {"g": -1}, [])), "a negative cap is rejected"
assert rejects(brief(10, 1, {"g": 1}, [["a"]])), "an item that is not a mapping"
assert rejects(
    brief(10, 1, {"g": 1}, [{"bytes": 1, "weight": 1, "family": "g"}])
), "a missing name is rejected"
assert rejects(
    brief(10, 1, {"g": 1}, [item("a", 1, 1, "g"), item("a", 2, 1, "g")])
), "a repeated name is rejected"
assert rejects(brief(10, 1, {"g": 1}, [item("a", 0, 1, "g")])), "bytes of zero"
assert rejects(brief(10, 1, {"g": 1}, [item("a", 1, -1, "g")])), "a negative weight"
assert rejects(brief(10, 1, {"g": 1}, [item("a", 1, 1, "q")])), "an unmentioned family"

print("ok")
