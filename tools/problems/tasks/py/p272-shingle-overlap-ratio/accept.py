from solution import shingle_overlap_ratio

assert shingle_overlap_ratio("the quick brown fox", "the quick brown dog", 2) == [
    1,
    2,
], "pairs of tokens, half shared"
assert shingle_overlap_ratio("the quick brown fox", "the quick brown dog", 1) == [
    3,
    5,
], "single tokens"
assert shingle_overlap_ratio("the quick brown fox", "the quick brown dog", 3) == [
    1,
    3,
], "triples of tokens"
assert shingle_overlap_ratio("p q r s", "r s t u", 1) == [1, 3], "two over six reduces"
assert shingle_overlap_ratio("alpha beta", "alpha beta", 2) == [1, 1], "identical"
assert shingle_overlap_ratio("a b", "c d", 2) == [0, 1], "nothing in common"
assert shingle_overlap_ratio("a b a b", "a b", 2) == [1, 2], "repeat counts once"
assert shingle_overlap_ratio("  one   two  three ", "one two three", 2) == [
    1,
    1,
], "runs of spaces collapse"
assert shingle_overlap_ratio("x y z", "y z x", 3) == [0, 1], "order matters"


def rejects(left, right, width):
    try:
        shingle_overlap_ratio(left, right, width)
    except ValueError:
        return True
    return False


assert rejects("a b", "c d", 0), "width zero is rejected"
assert rejects("a b", "c d", 2.5), "fractional width is rejected"
assert rejects("a b", "c d", 3), "width past the token count is rejected"
assert rejects("a b", "   ", 1), "a tokenless passage is rejected"
assert rejects(7, "c d", 1), "a non-string passage is rejected"
print("ok")
