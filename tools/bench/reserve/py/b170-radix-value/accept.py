from solution import radix_value

assert radix_value("2#1011") == 11, "a binary literal is decoded"
assert radix_value("16#ff") == 255, "letter digits carry their worths"
assert radix_value("10#0") == 0, "a lone zero is zero"
assert radix_value("2#0011") == 3, "leading zeros are legal"
assert radix_value("13#c0") == 156, "an uncommon base folds the same way"


def rejects(value):
    try:
        radix_value(value)
    except ValueError:
        return True
    return False


assert rejects(42), "a non-string literal is rejected"
assert rejects("1011"), "a literal without a hash mark is rejected"
assert rejects("17#0"), "a base above 16 is rejected"
assert rejects("2#"), "an empty digit part is rejected"
assert rejects("2#102"), "a digit at or above the base is rejected"
assert rejects("16#FF"), "an uppercase digit is rejected"
print("ok")
