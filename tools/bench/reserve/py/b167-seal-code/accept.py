from solution import seal_code

assert seal_code("7") == "7L", "a single digit is sealed"
assert seal_code("0") == "0E", "a zero code is sealed"
assert seal_code("A") == "AO", "a single letter is sealed"
assert seal_code("AB") == "ABN", "the worked example holds"
assert seal_code("BA") == "BAO", "the same characters in the other order seal differently"
assert seal_code("Z9") == "Z9Z", "the highest worths wrap under the modulus"
assert seal_code("DOCK31") == "DOCK31R", "a longer mixed code is sealed"


def rejects(value):
    try:
        seal_code(value)
    except ValueError:
        return True
    return False


assert rejects(42), "a non-string code is rejected"
assert rejects(""), "an empty code is rejected"
assert rejects("dock"), "a lowercase letter is rejected"
assert rejects("A-1"), "a character outside digits and capitals is rejected"
print("ok")
