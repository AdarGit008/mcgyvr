from solution import blend_congruences

assert blend_congruences([[2, 4], [4, 6]]) == [
    10,
    12,
], "spans sharing a factor merge on their least common multiple"
assert blend_congruences([[2, 3], [3, 5], [2, 7]]) == [
    23,
    105,
], "three spans sharing no factor"
assert blend_congruences([[1, 3], [2, 5], [3, 7], [4, 11]]) == [
    367,
    1155,
], "four spans merge to one value"
assert blend_congruences([[3, 4], [3, 6], [3, 9]]) == [
    3,
    36,
], "agreeing rests across overlapping spans"
assert blend_congruences([[1, 2], [2, 4]]) == [
], "conflicting congruences yield an empty list"
assert blend_congruences([[0, 6], [3, 4]]) == [
], "an odd rest against an even one cannot be reconciled"
assert blend_congruences([[7, 10]]) == [7, 10], "a lone pair merges to itself"
assert blend_congruences([[-3, 10]]) == [
    7,
    10,
], "an incoming rest is folded into its own span"
assert blend_congruences([[5, 1]]) == [
    0,
    1,
], "a span of one leaves every unknown, reported as zero"
assert blend_congruences([[2, 4], [2, 4]]) == [
    2,
    4,
], "the same congruence twice merges to itself"


def rejects(pairs):
    try:
        blend_congruences(pairs)
    except ValueError:
        return True
    return False


assert rejects([[1, 999983], [2, 999979]]), "a merged span past the limit is rejected"
assert rejects([]), "an empty list of pairs is rejected"
assert rejects("pairs"), "a non-list argument is rejected"
assert rejects([[1, 0]]), "a span of nothing is rejected"
assert rejects([[1, -4]]), "a negative span is rejected"
assert rejects([[1, 1000001]]), "a span past the ceiling is rejected"
assert rejects([[1.5, 4]]), "a fractional rest is rejected"
assert rejects([[1000000001, 4]]), "a rest past the limit is rejected"
assert rejects([[1]]), "an entry that is not a pair is rejected"
print("ok")
