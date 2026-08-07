from solution import league_order

assert league_order(
    [["A", "B", 1, 0], ["B", "C", 5, 0], ["C", "D", 0, 0], ["A", "D", 0, 3]]
) == ["D", "A", "B", "C"], "the level-group recount beats a fatter goal difference"
assert league_order([["E", "F", 1, 1], ["E", "G", 3, 0], ["F", "G", 2, 0]]) == [
    "E",
    "F",
    "G",
], "after a drawn meeting, season goal difference decides"
assert league_order([["H", "I", 2, 2], ["H", "J", 3, 1], ["I", "J", 4, 2]]) == [
    "I",
    "H",
    "J",
], "with equal goal difference, goals scored decide"
assert league_order(
    [["gamma", "beta", 1, 0], ["beta", "alpha", 1, 0], ["alpha", "gamma", 1, 0]]
) == ["alpha", "beta", "gamma"], "a perfect cycle falls back to names"
assert league_order([["X", "Y", 2, 0]]) == ["X", "Y"], "one match, two places"
assert league_order([["m", "k", 0, 0]]) == ["k", "m"], "a bare draw is ranked alphabetically"


def rejects(matches):
    try:
        league_order(matches)
    except ValueError:
        return True
    return False


assert rejects([["A", "A", 1, 0]]), "self-match rejected"
assert rejects([["A", "B", -1, 0]]), "negative goals rejected"
assert rejects([["A", "B", 1.5, 0]]), "fractional goals rejected"
assert rejects([["A", "B", 1]]), "3-item entry rejected"
assert rejects([[7, "B", 1, 0]]), "non-string name rejected"
print("ok")
