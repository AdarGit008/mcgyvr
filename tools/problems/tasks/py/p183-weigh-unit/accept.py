from solution import weigh_unit

table = {"H": 1, "C": 12, "N": 14, "O": 16, "S": 32, "Mg": 24, "Uuo": 294}

assert weigh_unit("H", table) == 1, "one part, no count"
assert weigh_unit("H2O", table) == 18, "counts on plain names"
assert weigh_unit("Mg(OH)2", table) == 58, "a count scales only its wrapping"
assert weigh_unit("[NH4]2SO4", table) == 132, "square brackets behave the same"
assert weigh_unit("(C(H2)3)2", table) == 36, "wrappings nest"
assert weigh_unit("Uuo", table) == 294, "a three letter name"
assert weigh_unit("[H(O)]", table) == 17, "the two shapes mix when matched"
assert weigh_unit("H12", table) == 12, "a two digit count is one number"


def rejects(spec, masses=table):
    try:
        weigh_unit(spec, masses)
    except ValueError:
        return True
    return False


assert rejects("Xz"), "an absent name is rejected"
assert rejects("H(O]"), "a mismatched shape is rejected"
assert rejects("(H2O"), "an unanswered opener is rejected"
assert rejects("H2O)"), "a stray closer is rejected"
assert rejects("()"), "an empty wrapping is rejected"
assert rejects("H0"), "a zero count is rejected"
assert rejects("H02"), "a padded count is rejected"
assert rejects(""), "the empty spec is rejected"
assert rejects(7), "a non-string spec is rejected"
print("ok")
