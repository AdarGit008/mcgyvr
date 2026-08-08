from solution import rebuild_from_terms

assert rebuild_from_terms([4, 2, 6, 7]) == [415, 93], "the worked example"
assert rebuild_from_terms([3, 7, 16]) == [355, 113], "a famous quotient"
assert rebuild_from_terms([1, 2]) == [3, 2], "a two-entry run"
assert rebuild_from_terms([1]) == [1, 1], "a lone one"
assert rebuild_from_terms([0]) == [0, 1], "a lone zero keeps a denominator of one"
assert rebuild_from_terms([7]) == [7, 1], "a lone whole quantity"
assert rebuild_from_terms([0, 3]) == [1, 3], "a leading zero gives a small quotient"
assert rebuild_from_terms([-4, 2]) == [-7, 2], "a negative lead carries through"
assert rebuild_from_terms([-1, 1, 2]) == [
    -1,
    3,
], "the numerator may end up smaller in size than the lead"
assert rebuild_from_terms([1, 1, 1, 1, 2]) == [
    13,
    8,
], "a run of ones builds neighbouring counting quantities"
assert rebuild_from_terms([999, 1000, 1000]) == [
    999001999,
    1000001,
], "a run close to the swelling limit still rebuilds exactly"
assert rebuild_from_terms([2, 1, 1, 1, 2]) == [
    21,
    8,
], "ones in the middle of a run are ordinary entries"


def rejects(run):
    try:
        rebuild_from_terms(run)
    except ValueError:
        return True
    return False


assert rejects([]), "an empty run is rejected"
assert rejects("47"), "a run that is not a list is rejected"
assert rejects([1, 2, 1]), "a run ending in one is rejected"
assert rejects([1, 0]), "an entry of nothing behind the lead is rejected"
assert rejects([1, -3]), "a negative entry behind the lead is rejected"
assert rejects([1, 1001]), "an entry above the ceiling is rejected"
assert rejects([1000001]), "a leading entry too large is rejected"
assert rejects([1.5, 2]), "a fractional entry is rejected"
assert rejects([1000000, 1000, 1000]), "a run that swells past the limit is rejected"
assert rejects([2] * 65), "a run of more than 64 entries is rejected"
print("ok")
