from solution import zone_pick_walk


def at(code, zone, row, slot):
    return {"code": code, "zone": zone, "row": row, "slot": slot}


def plan(zone_order, picks):
    return {"zoneOrder": zone_order, "picks": picks}


def rejects(value):
    try:
        zone_pick_walk(value)
    except ValueError:
        return True
    return False


assert zone_pick_walk(plan(["a"], [])) == [], "no picks, no lines"
assert zone_pick_walk(plan(["a"], [at("p1", "a", 3, 2)])) == [
    "a/3:p1"
], "one pick makes one line"
assert zone_pick_walk(
    plan(["z"], [at("a", "z", 5, 9), at("b", "z", 5, 2), at("c", "z", 5, 6)])
) == ["z/5:b|c|a"], "the first row entered is taken facing up"
assert zone_pick_walk(
    plan(
        ["z"],
        [
            at("a", "z", 2, 1),
            at("b", "z", 2, 4),
            at("c", "z", 3, 1),
            at("d", "z", 3, 4),
        ],
    )
) == ["z/2:a|b", "z/3:d|c"], "the trolley turns about on the second row entered"
assert zone_pick_walk(
    plan(["back", "front"], [at("f", "front", 1, 1), at("k", "back", 1, 1)])
) == ["back/1:k", "front/1:f"], "zoneOrder decides the sequence"
assert zone_pick_walk(
    plan(["a", "b", "c"], [at("x", "c", 1, 1), at("y", "a", 1, 1)])
) == ["a/1:y", "c/1:x"], "a zone with no picks is passed over"
assert zone_pick_walk(
    plan(["z"], [at("late", "z", 1, 3), at("early", "z", 1, 3)])
) == ["z/1:late|early"], "a shared slot keeps the listed order"
assert zone_pick_walk(
    plan(
        ["z", "y"],
        [
            at("a", "z", 1, 5),
            at("b", "z", 1, 2),
            at("c", "z", 2, 5),
            at("d", "z", 2, 2),
            at("e", "z", 3, 5),
            at("f", "z", 3, 2),
            at("g", "y", 4, 5),
            at("h", "y", 4, 2),
            at("i", "y", 7, 5),
            at("j", "y", 7, 2),
        ],
    )
) == [
    "z/1:b|a",
    "z/2:c|d",
    "z/3:f|e",
    "y/4:h|g",
    "y/7:i|j",
], "the facing resets when a new zone is entered"

assert rejects([1, 2]), "a plan that is not a mapping is rejected"
assert rejects(plan([], [])), "an empty zoneOrder is rejected"
assert rejects(plan(["a", "a"], [])), "a repeated zone is rejected"
assert rejects(plan([7], [])), "a zone that is not a string is rejected"
assert rejects({"zoneOrder": ["a"], "picks": "none"}), "picks must be a list"
assert rejects(plan(["a"], [["a", 1]])), "a pick that is not a mapping is rejected"
assert rejects(plan(["a"], [{"zone": "a", "row": 1, "slot": 1}])), "a missing code"
assert rejects(
    plan(["a"], [at("k", "a", 1, 1), at("k", "a", 2, 1)])
), "a repeated code is rejected"
assert rejects(plan(["a"], [at("k", "b", 1, 1)])), "an unlisted zone is rejected"
assert rejects(plan(["a"], [at("k", "a", 0, 1)])), "row zero is rejected"
assert rejects(plan(["a"], [at("k", "a", 1, "3")])), "a slot that is not a number"

print("ok")
