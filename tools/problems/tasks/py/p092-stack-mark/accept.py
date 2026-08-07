from solution import canonical_stack_mark

assert canonical_stack_mark("3n17") == "3N017", "joined directly"
assert canonical_stack_mark("3-N-17") == "3N017", "hyphen separators"
assert canonical_stack_mark("3 n 017") == "3N017", "space separators, leading zero"
assert canonical_stack_mark("9w1") == "9W001", "single-digit stack pads to three"
assert canonical_stack_mark("5E999") == "5E999", "already canonical survives"
assert canonical_stack_mark("7s  042") == "7S042", "multiple spaces allowed"
assert canonical_stack_mark("2e-5") == "2E005", "mixed joining styles"


def rejects(value):
    try:
        canonical_stack_mark(value)
    except ValueError:
        return True
    return False


assert rejects(""), "empty string is rejected"
assert rejects("0n17"), "floor 0 is rejected"
assert rejects("3x17"), "unknown wing is rejected"
assert rejects("3n000"), "stack value 0 is rejected"
assert rejects("3n0017"), "four digits are rejected"
assert rejects("3--n17"), "double hyphen is rejected"
assert rejects("3n17b"), "trailing junk is rejected"
assert rejects(42), "non-string is rejected"
print("ok")
