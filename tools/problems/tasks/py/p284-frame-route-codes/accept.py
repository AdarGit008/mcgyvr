from solution import sort_postal_items

FRAME = [
    {"name": "one", "depot": "QNR", "low": 0, "high": 199},
    {"name": "two", "depot": "QNR", "low": 100, "high": 499},
    {"name": "three", "depot": "BLT", "low": 0, "high": 999},
]

assert sort_postal_items(["QNR-150"], FRAME) == [
    "one"
], "the earliest claiming bin wins, not the tightest"
assert sort_postal_items(["QNR-300", "BLT-000", "BLT-999"], FRAME) == [
    "two",
    "three",
    "three",
], "later bins and the ends of a range"
assert sort_postal_items(["QNR-700", "ZZZ-001"], FRAME) == [
    "HOLD",
    "HOLD",
], "a well-formed code no bin claims is held"
assert sort_postal_items(["blt-001", "QNR150", "QNR-1500", "", "QNR-15"], FRAME) == [
    "BAD",
    "BAD",
    "BAD",
    "BAD",
    "BAD",
], "broken grammar never reaches the frame"
assert sort_postal_items(["QNR-199", "QNR-200", "QNR-499", "QNR-500"], FRAME) == [
    "one",
    "two",
    "two",
    "HOLD",
], "range edges either side of the boundary"
assert sort_postal_items([], FRAME) == [], "an empty sack sorts to nothing"
assert sort_postal_items(
    ["BLT-042"], [{"name": "solo", "depot": "BLT", "low": 42, "high": 42}]
) == ["solo"], "a range of one walk"


def rejects(codes, bins):
    try:
        sort_postal_items(codes, bins)
    except ValueError:
        return True
    return False


assert rejects(["BLT-000"], []), "an empty frame"
assert rejects(
    ["BLT-000"],
    [
        {"name": "x", "depot": "BLT", "low": 0, "high": 9},
        {"name": "x", "depot": "QNR", "low": 0, "high": 9},
    ],
), "repeated bin name"
assert rejects(["BLT-000"], [{"name": "HOLD", "depot": "BLT", "low": 0, "high": 9}]), (
    "a bin named for a mark"
)
assert rejects(["BLT-000"], [{"name": "x", "depot": "Blt", "low": 0, "high": 9}]), (
    "a depot that is not three capitals"
)
assert rejects(["BLT-000"], [{"name": "x", "depot": "BLT", "low": 9, "high": 4}]), (
    "low above high"
)
assert rejects(["BLT-000"], [{"name": "x", "depot": "BLT", "low": 0, "high": 1000}]), (
    "a walk beyond 999"
)
assert rejects([7], FRAME), "a code that is not a string"
assert rejects("BLT-000", FRAME), "codes is not a list"
print("ok")
