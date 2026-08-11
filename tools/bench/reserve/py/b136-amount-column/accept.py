from solution import total_amounts

assert total_amounts(["1", "2"]) == "3", "two whole amounts"
assert total_amounts(["1.5", "2.25"]) == "3.75", "fractions align to the longest"
assert total_amounts(["0.99", "0.01"]) == "1.00", "carry crosses the dot"
assert total_amounts(["999", "1"]) == "1_000", "grouping appears in the total"
assert total_amounts(["1_204.50"]) == "1_204.50", "a lone amount comes back normalised"
assert (
    total_amounts(["9007199254740993", "0"]) == "9_007_199_254_740_993"
), "amounts beyond float precision stay exact"
assert total_amounts(["0", "0"]) == "0", "all zero stays zero"
assert total_amounts(["2", "0.125"]) == "2.125", "whole plus three fraction digits"
assert total_amounts(["4_5", "5"]) == "50", "input grouping need not be in threes"


def rejects(value):
    try:
        total_amounts(value)
    except ValueError:
        return True
    return False


assert rejects(42), "non-list argument is rejected"
assert rejects([]), "empty list is rejected"
assert rejects(["1", 2]), "non-string amount is rejected"
assert rejects([""]), "empty amount is rejected"
assert rejects([".5"]), "no digit before the dot is rejected"
assert rejects(["5."]), "no digit after the dot is rejected"
assert rejects(["1__2"]), "doubled underscore is rejected"
assert rejects(["1.2_3"]), "underscore in the fraction is rejected"
assert rejects(["-3"]), "stray character is rejected"
print("ok")
