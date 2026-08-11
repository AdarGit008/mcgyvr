from solution import fit_mask

assert fit_mask("AA-99", "ab-12") == "AB-12", "letters uppercase, digits keep"
assert fit_mask("(999) AA", "(407) pq") == "(407) PQ", "literals pass through"
assert fit_mask("9A9A", "1x2Y") == "1X2Y", "alternating slots fit in place"


def rejects(*args):
    try:
        fit_mask(*args)
    except ValueError:
        return True
    return False


assert rejects("AA", "abc"), "a text longer than its mask is rejected"
assert rejects("A-9", "a_7"), "a literal slot must match the mask"
assert rejects("AA", "a1"), "a digit cannot fill a letter slot"
assert rejects("99", "4x"), "a letter cannot fill a digit slot"
assert rejects("", ""), "an empty mask is rejected"
assert rejects("AA", 42), "a non-string text is rejected"
print("ok")
