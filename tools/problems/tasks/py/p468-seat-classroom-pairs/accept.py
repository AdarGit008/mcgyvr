from solution import seat_classroom

assert seat_classroom(
    {
        "rows": 2,
        "cols": 3,
        "pupils": ["ann", "bob", "cid"],
        "together": [["ann", "cid"]],
        "apart": [["ann", "bob"]],
    }
) == {
    "seated": True,
    "grid": [["ann", "cid", "bob"], ["", "", ""]],
}, "a glued pair sits side by side while a split pair is kept off it"

assert seat_classroom(
    {
        "rows": 2,
        "cols": 2,
        "pupils": ["w", "x", "y", "z"],
        "together": [["w", "z"]],
        "apart": [],
    }
) == {
    "seated": True,
    "grid": [["w", "x"], ["z", "y"]],
}, "a glued pair may sit one above the other"

assert seat_classroom(
    {
        "rows": 1,
        "cols": 3,
        "pupils": ["a", "b"],
        "together": [],
        "apart": [["a", "b"]],
    }
) == {
    "seated": True,
    "grid": [["a", "", "b"]],
}, "an empty desk is left between two who must be kept apart"

assert seat_classroom(
    {"rows": 1, "cols": 2, "pupils": ["zed", "amy"], "together": [], "apart": []}
) == {
    "seated": True,
    "grid": [["amy", "zed"]],
}, "the earliest name alphabetically takes the first desk"

assert seat_classroom(
    {"rows": 2, "cols": 2, "pupils": [], "together": [], "apart": []}
) == {
    "seated": True,
    "grid": [["", ""], ["", ""]],
}, "an empty roster fills nothing and still seats"

assert seat_classroom(
    {
        "rows": 1,
        "cols": 2,
        "pupils": ["ann", "bob"],
        "together": [],
        "apart": [["ann", "bob"]],
    }
) == {
    "seated": False,
    "grid": [],
}, "two desks, two pupils and one split pairing cannot be done"

assert seat_classroom(
    {"rows": 2, "cols": 1, "pupils": ["m", "n"], "together": [], "apart": [["m", "n"]]}
) == {
    "seated": False,
    "grid": [],
}, "desks stacked in a column neighbour each other too"

assert seat_classroom(
    {
        "rows": 1,
        "cols": 3,
        "pupils": ["a", "b", "c"],
        "together": [["a", "c"]],
        "apart": [["a", "b"], ["b", "c"]],
    }
) == {
    "seated": False,
    "grid": [],
}, "a row of three cannot satisfy all three pairings at once"


def rejects(room):
    try:
        seat_classroom(room)
    except ValueError:
        return True
    return False


assert rejects({"rows": 1, "cols": 1, "pupils": []}), "a room short of keys is rejected"
assert rejects(
    {"rows": 0, "cols": 3, "pupils": [], "together": [], "apart": []}
), "a grid with no rows is rejected"
assert rejects(
    {"rows": 1, "cols": 1, "pupils": ["a", "b"], "together": [], "apart": []}
), "more pupils than desks is rejected"
assert rejects(
    {"rows": 2, "cols": 2, "pupils": ["a", "a"], "together": [], "apart": []}
), "two pupils sharing a name are rejected"
assert rejects(
    {"rows": 2, "cols": 2, "pupils": ["a", "b"], "together": [["a", "q"]], "apart": []}
), "a pairing naming an outsider is rejected"
assert rejects(
    {"rows": 2, "cols": 2, "pupils": ["a", "b"], "together": [["a", "a"]], "apart": []}
), "a pairing naming one pupil twice is rejected"
assert rejects(
    {
        "rows": 2,
        "cols": 2,
        "pupils": ["a", "b"],
        "together": [["a", "b"], ["b", "a"]],
        "apart": [],
    }
), "the same pairing listed twice is rejected"
assert rejects(
    {
        "rows": 2,
        "cols": 2,
        "pupils": ["a", "b"],
        "together": [["a", "b"]],
        "apart": [["b", "a"]],
    }
), "a pairing in both lists is rejected"
assert rejects(
    {"rows": 2, "cols": 2, "pupils": ["a", "b"], "together": [["a"]], "apart": []}
), "a pairing of one name is rejected"
print("ok")
