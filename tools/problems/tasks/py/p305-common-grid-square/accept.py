from solution import common_grid_square


def rejects(references):
    try:
        common_grid_square(references)
    except ValueError:
        return True
    return False


assert (
    common_grid_square(["KM1234"]) == "KM1234"
), "a lone reference already is its own tightest box"
assert (
    common_grid_square(["KM1234", "KM1234"]) == "KM1234"
), "the same box twice does not loosen anything"
assert (
    common_grid_square(["KM1234", "KM1235"]) == "KM13"
), "neighbours to the north slacken by one figure"
assert (
    common_grid_square(["KM1234", "KM1256"]) == "KM"
), "boxes far apart inside the square fall back to the bare capitals"
assert (
    common_grid_square(["KM12", "KM1234"]) == "KM"
), "a coarse entry caps how tight the answer may be"
assert (
    common_grid_square(["KM", "KM1234"]) == "KM"
), "the coarsest entry is a whole square"
assert (
    common_grid_square(["KM123456", "KM123457"]) == "KM1245"
), "a three-figure pair slackens to two"
assert (
    common_grid_square(["AB012345", "AB012346"]) == "AB0134"
), "the answer keeps its leading nought"
assert (
    common_grid_square(["AA0000", "AA0001"]) == "AA00"
), "the origin corner slackens to a tenth of the square"
assert (
    common_grid_square(["AA", "BA"]) == ""
), "capitals that disagree leave nothing to hand back"
assert (
    common_grid_square(["AA9999999999", "BB0000000000"]) == ""
), "diagonal neighbours in different squares share no box"

assert rejects("KM1234"), "a bare string is not a list"
assert rejects([]), "an empty list is rejected"
assert rejects(["KM1234", 12]), "a number among the references is rejected"
assert rejects(["KM1234", "IA12"]), "a struck-out capital is rejected"
assert rejects(["KM1234", "KM123"]), "an odd tally of figures is rejected"
assert rejects(["KM123456789012"]), "twelve figures overshoot the projection"
print("ok")
