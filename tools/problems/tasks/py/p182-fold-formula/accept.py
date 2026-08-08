from solution import fold_formula

assert fold_formula("C") == "C", "a lone tag keeps no count"
assert fold_formula("H2O") == "H2O", "flat recipe, tags already ordered"
assert fold_formula("OH2") == "H2O", "tags are reordered by code point"
assert fold_formula("H1") == "H", "an explicit repeat of one prints nothing"
assert fold_formula("Mg(OH)2") == "H2MgO2", "group repeat multiplies inside"
assert fold_formula("K4(ON(SO3)2)2") == "K4N2O14S4", "nested groups multiply through"
assert fold_formula("((H)2)3") == "H6", "repeats compose across depths"
assert fold_formula("(Uue)3") == "Uue3", "a three-letter tag is legal"
assert fold_formula("CaCO3") == "CCaO3", "one and two letter tags sort apart"
assert fold_formula("NaClNaCl") == "Cl2Na2", "a repeated tag accumulates"
assert fold_formula("(NH4)2SO4") == "H8N2O4S", "a group followed by more items"
assert fold_formula("H12") == "H12", "a two digit repeat is one number"


def rejects(value):
    try:
        fold_formula(value)
    except ValueError:
        return True
    return False


assert rejects(""), "the empty recipe is rejected"
assert rejects("(H2O"), "an open parenthesis is rejected"
assert rejects("H2O)"), "a lone closer is rejected"
assert rejects("()"), "an empty group is rejected"
assert rejects("H0"), "a zero repeat is rejected"
assert rejects("H02"), "a leading zero is rejected"
assert rejects("h2o"), "a lowercase start is rejected"
assert rejects("Uuea"), "a four letter tag is rejected"
assert rejects(42), "a non-string is rejected"
print("ok")
