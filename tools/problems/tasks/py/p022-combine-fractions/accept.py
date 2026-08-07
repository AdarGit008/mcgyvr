from solution import combine_fractions

assert combine_fractions(["1/2", "1/3"]) == "5/6", "simple sum"
assert combine_fractions(["1/4", "1/4"]) == "1/2", "sum is reduced"
assert combine_fractions(["2/4"]) == "1/2", "single entry is reduced"
assert combine_fractions(["1/2", "-1/2"]) == "0/1", "zero is 0/1"
assert combine_fractions(["-1/6", "-1/6"]) == "-1/3", "negative total"
assert combine_fractions(["3/1", "1/2"]) == "7/2", "improper total kept as n/d"
assert combine_fractions(["5/10", "1/10", "2/5"]) == "1/1", "whole total keeps /1"
assert combine_fractions(["0/7"]) == "0/1", "zero entry normalises"


def rejects(value):
    try:
        combine_fractions(value)
    except ValueError:
        return True
    return False


assert rejects([]), "empty list is rejected"
assert rejects(["1/0"]), "zero denominator is rejected"
assert rejects(["1/-2"]), "signed denominator is rejected"
assert rejects(["one/2"]), "non-numeric part is rejected"
assert rejects(["1/2", "3"]), "missing slash is rejected"
print("ok")
