from solution import cents_of


def rejects(value):
    try:
        cents_of(value)
    except Exception:
        return True
    return False


assert cents_of("12") == 1200, "a bare whole part reads as whole cents"
assert cents_of("1,234.5") == 123450, "one decimal digit counts tenths"
assert cents_of("-0.07") == -7, "a minus sign turns the count negative"
assert cents_of("1234.56") == 123456, "an ungrouped whole part with two decimals"
assert cents_of("1,000,000") == 100000000, "several groups of three read as one number"
assert rejects("12,34"), "a group of the wrong width is rejected"
assert rejects(42), "an amount that is not a string is rejected"
print("ok")
