from solution import stamp_cover, stamp_table

assert stamp_cover("abab", [["ab", 3], ["a", 2], ["b", 2]]) == 6, "repeating dies"
assert (
    stamp_cover("abc", [["ab", 5], ["c", 2], ["abc", 9], ["a", 1], ["bc", 3]]) == 4
), "the cheapest split beats the one-die press"
assert (
    stamp_cover("panel", [["pan", 6], ["el", 2], ["panel", 7]]) == 7
), "one die may cover the whole label"
assert (
    stamp_cover("aaaa", [["aaa", 1], ["aa", 2], ["a", 5]]) == 4
), "the longest die first is not always cheapest"
assert stamp_table([["ab", 3], ["c", 1]]) == {
    "ab": 3,
    "c": 1,
}, "the helper builds the price lookup"


def rejects(label, dies):
    try:
        stamp_cover(label, dies)
    except Exception:
        return True
    return False


assert rejects(42, [["a", 1]]), "non-string label is rejected"
assert rejects("", [["a", 1]]), "empty label is rejected"
assert rejects("xy", [["x", 1]]), "an unspellable label is rejected"
assert rejects("x", [["x", 1], ["x", 2]]), "a die listed twice is rejected"
assert rejects("x", [["", 1]]), "an empty fragment is rejected"
assert rejects("x", [["x", 0]]), "a zero price is rejected"
assert rejects("x", [["x", 1.5]]), "a fractional price is rejected"
print("ok")
