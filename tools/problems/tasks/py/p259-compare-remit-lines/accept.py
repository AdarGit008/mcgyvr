from solution import compare_remit_lines

ours = [["INV-1", 1000], ["INV-2", 2500], ["INV-3", -400]]
theirs = [["INV-2", 2500], ["INV-3", -450], ["INV-9", 700]]

assert compare_remit_lines(ours, theirs) == {
    "agreed": ["INV-2"],
    "queried": ["INV-3"],
    "ourSide": ["INV-1"],
    "theirSide": ["INV-9"],
}, "one of each outcome"
assert compare_remit_lines([], []) == {
    "agreed": [],
    "queried": [],
    "ourSide": [],
    "theirSide": [],
}, "two empty advices agree on nothing"
assert compare_remit_lines(ours, []) == {
    "agreed": [],
    "queried": [],
    "ourSide": ["INV-1", "INV-2", "INV-3"],
    "theirSide": [],
}, "an empty counterparty advice leaves everything on our side"
assert compare_remit_lines([], theirs) == {
    "agreed": [],
    "queried": [],
    "ourSide": [],
    "theirSide": ["INV-2", "INV-3", "INV-9"],
}, "an empty advice of ours leaves everything on theirs"
assert compare_remit_lines([["c", 0], ["a", 0]], [["a", 0], ["c", 1]]) == {
    "agreed": ["a"],
    "queried": ["c"],
    "ourSide": [],
    "theirSide": [],
}, "zero is an amount like any other and the lists come back sorted"
assert compare_remit_lines([["x", -5]], [["x", 5]]) == {
    "agreed": [],
    "queried": ["x"],
    "ourSide": [],
    "theirSide": [],
}, "the same size with the opposite sign is queried"
assert compare_remit_lines([["z", 12], ["y", 12], ["w", 3]], [["w", 4], ["y", 12]]) == {
    "agreed": ["y"],
    "queried": ["w"],
    "ourSide": ["z"],
    "theirSide": [],
}, "several lines split across the four buckets"


def rejects(a, b):
    try:
        compare_remit_lines(a, b)
    except ValueError:
        return True
    return False


assert rejects([["a", 1], ["a", 2]], []), "a repeated label is rejected"
assert rejects([["", 1]], []), "an empty label is rejected"
assert rejects([[7, 1]], []), "a non-string label is rejected"
assert rejects([["a", 1.5]], []), "a fractional amount is rejected"
assert rejects([["a", 1, 2]], []), "a three-entry line is rejected"
assert rejects([["a"]], []), "a one-entry line is rejected"
assert rejects("a", []), "a string advice is rejected"
print("ok")
