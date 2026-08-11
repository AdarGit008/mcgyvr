from solution import assign_bins

assert assign_bins([["logs", ["*.log"]]], ["a.log", "b.txt"]) == {
    "bins": {"logs": ["a.log"]},
    "leftover": ["b.txt"],
}, "a leading-star pattern bins its matches"
assert assign_bins([["errs", ["err*"]]], ["err42", "warn7"]) == {
    "bins": {"errs": ["err42"]},
    "leftover": ["warn7"],
}, "a trailing-star pattern bins its matches"
assert assign_bins([["exact", ["core"]]], ["core", "core2"]) == {
    "bins": {"exact": ["core"]},
    "leftover": ["core2"],
}, "a starless pattern matches only its exact text"
assert assign_bins([["wrap", ["ab*ba"]]], ["abba", "abcba", "aba"]) == {
    "bins": {"wrap": ["abba", "abcba"]},
    "leftover": ["aba"],
}, "middle-star literal parts must not overlap"
assert assign_bins([["first", ["a*"]], ["second", ["*z"]]], ["az"]) == {
    "bins": {"first": ["az"], "second": []},
    "leftover": [],
}, "only the first matching rule takes the item"
assert assign_bins([["all", ["*"]]], ["", "x"]) == {
    "bins": {"all": ["", "x"]},
    "leftover": [],
}, "a bare star matches everything in input order"
assert assign_bins([], ["a"]) == {
    "bins": {},
    "leftover": ["a"],
}, "no rules leaves every item over"


def rejects(rules, items):
    try:
        assign_bins(rules, items)
    except ValueError:
        return True
    return False


assert rejects("x", []), "non-list rules are rejected"
assert rejects([["a"]], []), "a one-item rule is rejected"
assert rejects([["", ["x"]]], []), "an empty rule name is rejected"
assert rejects([["a", ["x"]], ["a", ["y"]]], []), "a repeated rule name is rejected"
assert rejects([["a", []]], []), "an empty patterns list is rejected"
assert rejects([["a", [""]]], []), "an empty pattern is rejected"
assert rejects([["a", ["x*y*"]]], []), "a two-star pattern is rejected"
assert rejects([["a", ["x"]]], [3]), "a non-string item is rejected"
print("ok")
