from solution import classify_hump_cars


def rejects(cut, table):
    try:
        classify_hump_cars(cut, table)
    except ValueError:
        return True
    return False


assert classify_hump_cars(
    [["c1", "north"], ["c2", "south"], ["c3", "north"], ["c4", "east"]],
    {"north": 3, "south": 1, "east": 3},
) == {"train": ["c2", "c1", "c3", "c4"], "unrouted": []}, (
    "track 1 is drawn before track 3 and each track keeps arrival order"
)

assert classify_hump_cars([["a", "x"], ["b", "x"], ["c", "x"]], {"x": 2}) == {
    "train": ["a", "b", "c"],
    "unrouted": [],
}, "one track is drawn off in the order the cars arrived"

assert classify_hump_cars(
    [["a", "far"], ["b", "near"]], {"far": 9, "near": 2}
) == {"train": ["b", "a"], "unrouted": []}, "the track used first is not drawn first"

assert classify_hump_cars(
    [["a", "x"], ["b", "unknown"], ["c", "x"]], {"x": 1}
) == {"train": ["a", "c"], "unrouted": ["b"]}, (
    "an unchalked destination goes to the rejection track"
)

assert classify_hump_cars([["a", "q"]], {}) == {
    "train": [],
    "unrouted": ["a"],
}, "an empty routing table rejects everything"

assert classify_hump_cars(
    [["w1", "ore"], ["w2", "coal"], ["w3", "ore"], ["w4", "grain"], ["w5", "coal"]],
    {"ore": 12, "coal": 4, "grain": 7},
) == {"train": ["w2", "w5", "w4", "w1", "w3"], "unrouted": []}, (
    "track numbers order numerically, not as written"
)

assert rejects("c1", {"x": 1}), "the cut must be a list"
assert rejects([], {"x": 1}), "an empty cut is rejected"
assert rejects([["a"]], {"x": 1}), "a one-part entry is rejected"
assert rejects([["a", ""]], {"x": 1}), "an empty destination is rejected"
assert rejects([[5, "x"]], {"x": 1}), "a non-string car number is rejected"
assert rejects([["a", "x"], ["a", "x"]], {"x": 1}), "a repeated car number is rejected"
assert rejects([["a", "x"]], [1, 2]), "a list is no routing table"
assert rejects([["a", "x"]], {"x": 0}), "track zero is rejected"
assert rejects([["a", "x"]], {"x": 1.5}), "a fractional track is rejected"
print("ok")
