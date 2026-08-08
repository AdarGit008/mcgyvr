from solution import assign_freed_slots


def one(name, tier, waited, window):
    return {"name": name, "tier": tier, "waited": waited, "window": window}


def call(slot, part):
    return {"slot": slot, "part": part}


def rejects(standby, cancellations):
    try:
        assign_freed_slots(standby, cancellations)
    except ValueError:
        return True
    return False


assert assign_freed_slots([], []) == [], "no calls, no placements"
assert assign_freed_slots(
    [one("eve", "urgent", 5, "afternoon")], [call("m9", "morning")]
) == [], "a slot nobody can take is passed over"
assert assign_freed_slots(
    [one("fay", "soon", 1, "either")],
    [call("s1", "morning"), call("s2", "morning")],
) == [{"slot": "s1", "name": "fay"}], (
    "a placed patient is off the list and takes no second slot"
)
assert assign_freed_slots(
    [one("gil", "routine", 90, "either"), one("hen", "urgent", 1, "either")],
    [call("s1", "morning")],
) == [{"slot": "s1", "name": "hen"}], (
    "urgent outranks ninety days of routine waiting"
)
assert assign_freed_slots(
    [one("ida", "soon", 4, "either"), one("jay", "soon", 11, "either")],
    [call("s1", "afternoon")],
) == [{"slot": "s1", "name": "jay"}], "inside one tier the longer wait wins"
assert assign_freed_slots(
    [one("kim", "soon", 7, "either"), one("lee", "soon", 7, "either")],
    [call("s1", "afternoon")],
) == [{"slot": "s1", "name": "kim"}], (
    "a level pair goes to whoever stands nearer the front"
)
assert assign_freed_slots(
    [
        one("ann", "routine", 40, "either"),
        one("bob", "urgent", 2, "morning"),
        one("cal", "soon", 30, "afternoon"),
        one("dee", "soon", 30, "either"),
    ],
    [
        call("m1", "morning"),
        call("a1", "afternoon"),
        call("a2", "afternoon"),
        call("m2", "morning"),
    ],
) == [
    {"slot": "m1", "name": "bob"},
    {"slot": "a1", "name": "cal"},
    {"slot": "a2", "name": "dee"},
    {"slot": "m2", "name": "ann"},
], "four calls empty the standby list in tier order"
assert assign_freed_slots(
    [one("mac", "urgent", 3, "morning"), one("nia", "routine", 0, "afternoon")],
    [call("a7", "afternoon")],
) == [{"slot": "a7", "name": "nia"}], (
    "an urgent patient who cannot come that half-day is out of the running"
)

assert rejects("x", []), "the standby list is a list"
assert rejects([], "x"), "the calls are a list"
assert rejects([one("pat", "later", 1, "either")], []), "later is no tier"
assert rejects([one("pat", "soon", 1, "evening")], []), "evening is no window"
assert rejects([one("pat", "soon", -2, "either")], []), "waited is never negative"
assert rejects(
    [one("pat", "soon", 1, "either"), one("pat", "urgent", 2, "either")], []
), "two patients may not share a name"
assert rejects([], [call("s1", "evening")]), "a call names morning or afternoon"
assert rejects([], [call("s1", "morning"), call("s1", "afternoon")]), (
    "two calls may not share a slot id"
)
print("ok")
