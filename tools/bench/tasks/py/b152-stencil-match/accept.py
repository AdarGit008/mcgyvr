from solution import matches_stencil

assert matches_stencil("FR-##", "FR-07") is True, "digit slots take digits"
assert matches_stencil("FR-##", "FR-x7") is False, "a letter cannot fill a digit slot"
assert matches_stencil("@@-#", "Ab-4") is True, "letter slots take either case"
assert matches_stencil("@@-#", "a2-4") is False, "a digit cannot fill a letter slot"
assert matches_stencil("bay?", "bay7") is True, "the wildcard takes any character"
assert matches_stencil("bay", "bay") is True, "plain characters match themselves"
assert matches_stencil("Bay", "bay") is False, "literal matching is case-sensitive"
assert matches_stencil("##", "123") is False, "a longer code never matches"


def rejects(stencil, code):
    try:
        matches_stencil(stencil, code)
    except ValueError:
        return True
    return False


assert rejects(9, "9"), "a non-string stencil is rejected"
assert rejects("", ""), "an empty stencil is rejected"
assert rejects("##", 12), "a non-string code is rejected"
print("ok")
