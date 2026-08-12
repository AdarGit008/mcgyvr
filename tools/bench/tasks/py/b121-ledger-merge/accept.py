from solution import merge_ledgers

assert merge_ledgers([["a", 100]], [["a", 120]], [["a", 90]]) == [
    ["a", 110]
], "both sides' deltas apply"
assert merge_ledgers([["a", 100]], [["a", 100]], [["a", 70]]) == [
    ["a", 70]
], "one side's edit carries"
assert merge_ledgers([["a", 100]], [["a", 100]], [["a", 100]]) == [
    ["a", 100]
], "untouched account keeps its value"
assert merge_ledgers([["a", 50]], [["a", 0]], [["a", 10]]) == [
    ["a", -40]
], "joint withdrawals may overdraw"
assert merge_ledgers([], [["n", 25]], []) == [["n", 25]], "added by ours"
assert merge_ledgers([], [], [["p", 8]]) == [["p", 8]], "added by theirs"
assert merge_ledgers([], [["n", 25]], [["n", 30]]) == [
    ["n", 55]
], "added by both sums the two values"
assert merge_ledgers([["a", 40]], [], [["a", 40]]) == [
], "deletion beside an untouched copy holds"
assert merge_ledgers([["a", 40]], [], [["a", 45]]) == [
    ["a", 45]
], "an edit outlives the other side's deletion"
assert merge_ledgers([["a", 40]], [], []) == [], "dropped by both stays gone"
assert merge_ledgers(
    [["b", 10], ["a", 5]],
    [["b", 12], ["a", 5], ["c", 3]],
    [["b", 10], ["a", 8]],
) == [["a", 8], ["b", 12], ["c", 3]], "merged ledger comes back sorted by account"
assert merge_ledgers([], [], []) == [], "three empty ledgers merge to nothing"


def rejects(*args):
    try:
        merge_ledgers(*args)
    except Exception:
        return True
    return False


assert rejects("cash", [], []), "non-list ledger"
assert rejects([["", 1]], [], []), "empty account name"
assert rejects([], [["a", 1.5]], []), "fractional cents"
assert rejects([], [], [["a", 1, 2]]), "three-item entry"
assert rejects([["a", 1], ["a", 2]], [], []), "repeated account"
print("ok")
