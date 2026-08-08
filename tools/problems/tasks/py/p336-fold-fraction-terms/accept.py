from solution import fold_fraction_terms

assert fold_fraction_terms(415, 93) == [4, 2, 6, 7], "the worked example"
assert fold_fraction_terms(355, 113) == [3, 7, 16], "a famous quotient"
assert fold_fraction_terms(3, 2) == [1, 2], "a two-entry run"
assert fold_fraction_terms(1, 1) == [1], "one folds to a single entry"
assert fold_fraction_terms(0, 5) == [0], "nothing folds to a lone zero"
assert fold_fraction_terms(7, 1) == [7], "a whole quantity folds to itself"
assert fold_fraction_terms(1, 3) == [0, 3], "a leading zero is allowed"
assert fold_fraction_terms(-7, 2) == [-4, 2], "flooring runs downward"
assert fold_fraction_terms(-1, 3) == [
    -1,
    1,
    2,
], "a small negative quotient leans on the downward floor"
assert fold_fraction_terms(6, 4) == [
    1,
    2,
], "a quotient not in lowest terms folds the same as its reduced form"
assert fold_fraction_terms(1000000000, 999999999) == [
    1,
    999999999,
], "the size limit folds exactly"
assert fold_fraction_terms(13, 8) == [
    1,
    1,
    1,
    1,
    2,
], "neighbouring counting quantities give a run of ones ending in two"


def rejects(numerator, denominator):
    try:
        fold_fraction_terms(numerator, denominator)
    except ValueError:
        return True
    return False


assert rejects(1, 0), "a denominator of nothing is rejected"
assert rejects(1, -3), "a negative denominator is rejected"
assert rejects(1.5, 2), "a fractional numerator is rejected"
assert rejects(1, 2.5), "a fractional denominator is rejected"
assert rejects(1000000001, 2), "a numerator past the limit is rejected"
assert rejects(1, 1000000001), "a denominator past the limit is rejected"
assert rejects("415", 93), "a non-numeric argument is rejected"
print("ok")
