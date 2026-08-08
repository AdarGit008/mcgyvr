from solution import fold_dimension_terms


def term(op, count, units):
    return {"op": op, "count": count, "units": units}


def rejects(terms):
    try:
        fold_dimension_terms(terms)
    except ValueError:
        return True
    return False


assert fold_dimension_terms([term("=", 6, {"glim": 1})]) == {
    "count": 6,
    "units": {"glim": 1},
}, "one term is the running quantity already"

assert fold_dimension_terms(
    [term("=", 6, {"glim": 1}), term("*", 5, {"spen": 1})]
) == {"count": 30, "units": {"glim": 1, "spen": 1}}, "multiplying gathers both unit names"

assert fold_dimension_terms(
    [term("=", 12, {"glim": 2}), term("/", 4, {"glim": 1})]
) == {"count": 3, "units": {"glim": 1}}, "dividing takes an exponent away"

assert fold_dimension_terms(
    [term("=", 10, {"glim": 1}), term("/", 5, {"glim": 1})]
) == {
    "count": 2,
    "units": {},
}, "an exponent driven to zero leaves the answer entirely"

assert fold_dimension_terms(
    [term("=", 2, {"glim": 1}), term("*", 3, {"glim": -1})]
) == {"count": 6, "units": {}}, "a negative exponent cancels a positive one"

assert fold_dimension_terms(
    [term("=", 3, {"glim": 1, "spen": -1}), term("+", 4, {"spen": -1, "glim": 1})]
) == {
    "count": 7,
    "units": {"glim": 1, "spen": -1},
}, "like quantities add however their names are arranged"

assert fold_dimension_terms(
    [term("=", 3, {"glim": 1}), term("-", 5, {"glim": 1})]
) == {"count": -2, "units": {"glim": 1}}, "taking away may leave the count below zero"

assert fold_dimension_terms([term("=", 5, {}), term("*", 4, {"thod": 2})]) == {
    "count": 20,
    "units": {"thod": 2},
}, "a quantity with no dimension may still pick one up"

assert fold_dimension_terms(
    [term("=", 0, {"glim": 1}), term("*", -3, {})]
) == {"count": 0, "units": {"glim": 1}}, "a count of nothing stays plain zero"

assert fold_dimension_terms(
    [term("=", 100, {"glim": 1}), term("/", 4, {"spen": 1}), term("*", 3, {})]
) == {
    "count": 75,
    "units": {"glim": 1, "spen": -1},
}, "a chain of terms folds left to right"

assert fold_dimension_terms(
    [term("=", -6, {"glim": 1}), term("/", -2, {})]
) == {"count": 3, "units": {"glim": 1}}, "two negatives divide out whole"

assert rejects([]), "an empty term list is rejected"
assert rejects([term("*", 2, {})]), "a first op that is not = is rejected"
assert rejects([term("=", 2, {}), term("^", 2, {})]), "an op outside the four is rejected"
assert rejects(
    [term("=", 7, {}), term("/", 2, {})]
), "a division that does not come out whole is rejected"
assert rejects(
    [term("=", 7, {}), term("/", 0, {})]
), "dividing by a count of zero is rejected"
assert rejects(
    [term("=", 3, {"glim": 1}), term("+", 4, {"spen": 1})]
), "adding a different unit name is rejected"
assert rejects(
    [term("=", 3, {"glim": 1}), term("-", 4, {"glim": 2})]
), "adding the same name at another exponent is rejected"
assert rejects([term("=", 1.5, {})]), "a fractional count is rejected"
assert rejects([term("=", 2, {"glim": 0})]), "an exponent of zero is rejected"
assert rejects([term("=", 2, {"glim": 1.5})]), "a fractional exponent is rejected"
assert rejects(
    [term("=", 2, {"Glim": 1})]
), "a unit name outside the small letters is rejected"
assert rejects([term("=", 2, "glim")]), "units that are not a mapping are rejected"
assert rejects(["="]), "a term that is not a mapping is rejected"
assert rejects("terms"), "terms that are not a list are rejected"
print("ok")
