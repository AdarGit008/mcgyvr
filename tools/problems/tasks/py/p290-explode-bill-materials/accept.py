from solution import explode_bill_of_materials

WORKS = [
    {"part": "bike", "uses": [{"part": "wheel", "per": 2}, {"part": "frame", "per": 1}]},
    {"part": "wheel", "uses": [{"part": "spoke", "per": 8}, {"part": "rim", "per": 1}]},
    {"part": "frame", "uses": [{"part": "tube", "per": 4}]},
]

assert explode_bill_of_materials(WORKS, "bike", 1) == [
    {"part": "rim", "count": 2},
    {"part": "spoke", "count": 16},
    {"part": "tube", "count": 4},
], "one whole assembly down to raw stock"
assert explode_bill_of_materials(WORKS, "bike", 3) == [
    {"part": "rim", "count": 6},
    {"part": "spoke", "count": 48},
    {"part": "tube", "count": 12},
], "the batch multiplies every leaf"
assert explode_bill_of_materials(WORKS, "wheel", 1) == [
    {"part": "rim", "count": 1},
    {"part": "spoke", "count": 8},
], "a sub-assembly may be the root"
assert explode_bill_of_materials(WORKS, "spoke", 5) == [
    {"part": "spoke", "count": 5}
], "raw stock as the root is its own answer"
assert explode_bill_of_materials(
    [
        {"part": "cart", "uses": [{"part": "axle", "per": 2}, {"part": "bed", "per": 1}]},
        {"part": "axle", "uses": [{"part": "pin", "per": 3}]},
        {"part": "bed", "uses": [{"part": "pin", "per": 5}, {"part": "plank", "per": 6}]},
    ],
    "cart",
    1,
) == [
    {"part": "pin", "count": 11},
    {"part": "plank", "count": 6},
], "stock wanted by two branches is summed once"
assert explode_bill_of_materials(
    [
        {"part": "a", "uses": [{"part": "b", "per": 2}]},
        {"part": "b", "uses": [{"part": "c", "per": 3}]},
        {"part": "c", "uses": [{"part": "d", "per": 5}]},
    ],
    "a",
    2,
) == [{"part": "d", "count": 60}], "the per counts multiply the whole way down"
assert explode_bill_of_materials(
    [
        {"part": "lamp", "uses": [{"part": "glass", "per": 1}]},
        {"part": "x", "uses": [{"part": "y", "per": 1}]},
        {"part": "y", "uses": [{"part": "x", "per": 1}]},
    ],
    "lamp",
    1,
) == [{"part": "glass", "count": 1}], "a loop the root never reaches is no concern"


def rejects(parts, root, batch):
    try:
        explode_bill_of_materials(parts, root, batch)
    except ValueError:
        return True
    return False


assert rejects(
    [
        {"part": "x", "uses": [{"part": "y", "per": 1}]},
        {"part": "y", "uses": [{"part": "x", "per": 1}]},
    ],
    "x",
    1,
), "a two-part loop"
assert rejects([{"part": "a", "uses": [{"part": "a", "per": 1}]}], "a", 1), (
    "a part that swallows itself"
)
assert rejects("works", "a", 1), "parts is not a list"
assert rejects(
    [
        {"part": "a", "uses": [{"part": "b", "per": 1}]},
        {"part": "a", "uses": [{"part": "c", "per": 1}]},
    ],
    "a",
    1,
), "the same part named twice"
assert rejects([{"part": "", "uses": [{"part": "b", "per": 1}]}], "a", 1), (
    "an empty part name"
)
assert rejects([{"part": "a", "uses": []}], "a", 1), "an assembly that swallows nothing"
assert rejects(
    [{"part": "a", "uses": [{"part": "b", "per": 1}, {"part": "b", "per": 2}]}], "a", 1
), "the same sub-part named twice in one entry"
assert rejects([{"part": "a", "uses": [{"part": "b", "per": 0}]}], "a", 1), (
    "a per of nothing"
)
assert rejects([{"part": "a", "uses": [{"part": "b", "per": 1.5}]}], "a", 1), (
    "a fractional per"
)
assert rejects(WORKS, "", 1), "an empty root"
assert rejects(WORKS, "bike", 0), "a batch of none"
print("ok")
