from solution import balance_reaction


def rejects(value):
    try:
        balance_reaction(value)
    except ValueError:
        return True
    return False


assert balance_reaction("H2 + O2 -> H2O") == "2 H2 + O2 -> 2 H2O", (
    "water from its parts"
)
assert balance_reaction("N2 + H2 -> NH3") == "N2 + 3 H2 -> 2 NH3", (
    "a number of one is dropped"
)
assert balance_reaction("Fe + O2 -> Fe2O3") == "4 Fe + 3 O2 -> 2 Fe2O3", (
    "two-letter symbols and larger numbers"
)
assert balance_reaction("CH4 + O2 -> CO2 + H2O") == "CH4 + 2 O2 -> CO2 + 2 H2O", (
    "four species, two of them on the right"
)
assert balance_reaction("C + O2 -> CO") == "2 C + O2 -> 2 CO", "a bare symbol"
assert balance_reaction("H2O -> H2O") == "H2O -> H2O", (
    "the same species on both sides needs nothing"
)
assert balance_reaction("H2O -> H2O2") == "", "no positive numbers can settle this"
assert balance_reaction("C + H2 -> CH4 + O2") == "", (
    "a symbol reaching only one side"
)
assert balance_reaction("C8H18 + O2 -> CO2 + H2O") == "", (
    "the smallest answer runs past twelve"
)

assert rejects(7), "not a string"
assert rejects("H2 + O2"), "no arrow"
assert rejects("H2 -> O2 -> H3"), "two arrows"
assert rejects(" -> H2O"), "an empty side"
assert rejects("h2 -> h2"), "a small first letter"
assert rejects("H1 -> H1"), "a count of one"
assert rejects("H02 -> H02"), "a leading zero"
assert rejects("H2 + H2 -> H2O2"), "the same species listed twice"
assert rejects("H + C + N -> O + S + P"), "more than five species"
print("ok")
