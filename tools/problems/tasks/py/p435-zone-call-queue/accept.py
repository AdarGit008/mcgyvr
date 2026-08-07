from solution import build_zone_queue


def one(name, zone, party, early):
    return {"name": name, "zone": zone, "party": party, "early": early}


def rejects(zones, travellers):
    try:
        build_zone_queue(zones, travellers)
    except ValueError:
        return True
    return False


assert build_zone_queue(
    ["gold", "one", "two"],
    [
        one("ada", "two", "", False),
        one("bo", "gold", "kin", False),
        one("cy", "two", "kin", False),
        one("di", "one", "", True),
        one("ed", "one", "", False),
    ],
) == {"queue": ["di", "bo", "cy", "ed", "ada"], "calls": [2, 1, 1]}, (
    "the party walks with its earliest zone and is not called again"
)

assert build_zone_queue(
    ["a", "b"],
    [
        one("mo", "b", "fam", False),
        one("ny", "a", "fam", True),
        one("ox", "a", "", False),
    ],
) == {"queue": ["mo", "ny", "ox"], "calls": [1, 0]}, (
    "one early traveller pre-boards the whole party"
)

assert build_zone_queue(
    ["z"],
    [
        one("zed", "z", "", False),
        one("abe", "z", "", False),
        one("mel", "z", "", False),
    ],
) == {"queue": ["zed", "abe", "mel"], "calls": [3]}, (
    "empty party strings never join and keep desk order"
)

assert build_zone_queue(
    ["z"], [one("zoe", "z", "", True), one("amy", "z", "", True)]
) == {"queue": ["amy", "zoe"], "calls": [0]}, (
    "the pre-board block walks in name order, counting under no zone"
)

assert build_zone_queue(["p", "q"], []) == {"queue": [], "calls": [0, 0]}, (
    "nobody at the desk still reports one count per zone"
)

assert build_zone_queue(
    ["first", "second"],
    [
        one("hal", "second", "trio", False),
        one("gus", "second", "", False),
        one("ivy", "first", "trio", False),
        one("fay", "second", "trio", False),
    ],
) == {"queue": ["fay", "hal", "ivy", "gus"], "calls": [3, 1]}, (
    "a unit sorts its own members by name and is placed by its earliest member"
)

assert build_zone_queue(
    ["one", "two"],
    [
        one("kit", "two", "duo", False),
        one("lil", "one", "", False),
        one("nan", "two", "duo", False),
    ],
) == {"queue": ["lil", "kit", "nan"], "calls": [1, 2]}, (
    "a later zone still calls the units waiting for it in desk order"
)

assert rejects("gold", []), "the zones must be a list"
assert rejects(["a"], "x"), "the travellers must be a list"
assert rejects([], []), "no zones at all is rejected"
assert rejects(["a", ""], []), "an empty zone label is rejected"
assert rejects(["a", "a"], []), "a repeated zone label is rejected"
assert rejects(["a"], ["ada"]), "a traveller must be a mapping"
assert rejects(["a"], [one("", "a", "", False)]), "an empty name is rejected"
assert rejects(["a"], [one("sam", "a", "", False), one("sam", "a", "", False)]), (
    "a shared name is rejected"
)
assert rejects(["a"], [one("sam", "a", 4, False)]), "a non-string party is rejected"
assert rejects(["a"], [one("sam", "a", "", "yes")]), (
    "a non-boolean early flag is rejected"
)
assert rejects(["a"], [one("sam", "b", "", False)]), "an uncalled zone is rejected"
assert rejects(["a"], [{"zone": "a", "party": "", "early": False}]), (
    "a missing name is rejected"
)
print("ok")
