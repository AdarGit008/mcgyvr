from solution import commit_index

assert commit_index([1, 1, 2, 2], [4, 3, 1, 2], 2) == {
    "commit": 3,
    "safe": 1,
    "behind": [2, 3],
}, "three of five hold entry three, so that is as far as the log commits"
assert commit_index([1, 1, 2], [3, 3], 3) == {
    "commit": 0,
    "safe": 0,
    "behind": [],
}, "an entry from an older term never commits, however widely it is held"
assert commit_index([1, 2, 2], [], 2) == {
    "commit": 3,
    "safe": 3,
    "behind": [],
}, "a leader with no followers is its own quorum"
assert commit_index([], [0, 0], 4) == {
    "commit": 0,
    "safe": 0,
    "behind": [],
}, "an empty log commits nothing and hides nothing"
assert commit_index([5], [0, 0], 5) == {
    "commit": 0,
    "safe": 0,
    "behind": [],
}, "the leader alone is short of a quorum of three"
assert commit_index([5], [1, 0], 5) == {
    "commit": 1,
    "safe": 0,
    "behind": [1],
}, "one follower joining the leader carries the entry over the line"
assert commit_index([1, 1], [2, 2], 1) == {
    "commit": 2,
    "safe": 2,
    "behind": [],
}, "a fully replicated log may be discarded in full"
assert commit_index([1, 2], [2, 1], 2) == {
    "commit": 2,
    "safe": 1,
    "behind": [1],
}, "the laggard holds the snapshot point back below the commit"
assert commit_index([1, 1, 1, 2, 2, 2], [6, 5, 4, 2, 1], 2) == {
    "commit": 4,
    "safe": 1,
    "behind": [3, 4],
}, "four of six is the quorum, and entry four is the deepest one reaching it"


def rejects(log, matches, current_term):
    try:
        commit_index(log, matches, current_term)
    except ValueError:
        return True
    return False


assert rejects([2, 1], [0], 2), "a falling term is rejected"
assert rejects([5], [0], 3), "a term above the current one is rejected"
assert rejects([1, 1], [3], 1), "a copied number past the log is rejected"
assert rejects([1, 1], [-1], 1), "a negative copied number is rejected"
assert rejects([1, 1], [1.5], 1), "a fractional copied number is rejected"
assert rejects([0], [0], 1), "a term of zero is rejected"
assert rejects([1], [0], 0), "a current term of zero is rejected"
assert rejects("11", [0], 1), "a log given as text is rejected"
print("ok")
