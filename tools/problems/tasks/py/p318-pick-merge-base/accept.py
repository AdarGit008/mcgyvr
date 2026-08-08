from solution import pick_merge_base

HISTORY = {
    "a": [],
    "b": ["a"],
    "c": ["a"],
    "d": ["b", "c"],
    "e": ["b"],
    "f": ["c"],
}
CROSSED = {
    "r": [],
    "x": ["r"],
    "y": ["r"],
    "m": ["x", "y"],
    "n": ["y", "x"],
}


def rejects(parents, left, right):
    try:
        pick_merge_base(parents, left, right)
    except ValueError:
        return True
    return False


assert pick_merge_base(HISTORY, "e", "f") == "a", "two lines meet at the root"
assert pick_merge_base(HISTORY, "b", "c") == "a", "siblings meet at the root"
assert pick_merge_base(HISTORY, "d", "e") == "b", "the nearer forebear wins"
assert pick_merge_base(HISTORY, "b", "e") == "b", "a forebear of one is the answer"
assert pick_merge_base(HISTORY, "d", "d") == "d", "a revision against itself"
assert pick_merge_base(HISTORY, "a", "f") == "a", "the root against a leaf"
assert pick_merge_base(CROSSED, "m", "n") == "x", "alphabetical order settles a tie"
assert pick_merge_base(CROSSED, "m", "r") == "r", "the root is the only shared one"
assert rejects({"p": [], "q": []}, "p", "q"), "unrelated roots share nothing"
assert rejects(HISTORY, "a", "zz"), "an unknown revision"
assert rejects({"a": ["z"]}, "a", "a"), "an unknown parent"
assert rejects({"a": [], "b": ["a", "a"]}, "a", "b"), "the same parent named twice"
assert rejects({"u": ["v"], "v": ["u"]}, "u", "v"), "a revision descending from itself"
assert rejects({"a": "b"}, "a", "a"), "a parent list that is not a list"
assert rejects([], "a", "a"), "a history that is not a mapping"
print("ok")
