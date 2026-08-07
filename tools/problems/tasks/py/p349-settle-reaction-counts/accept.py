from solution import settle_reaction_counts


def rejects(*args):
    try:
        settle_reaction_counts(*args)
    except ValueError:
        return True
    return False


assert settle_reaction_counts([{"H": 2}, {"O": 2}], [{"H": 2, "O": 1}]) == [
    2,
    1,
    2,
], "three species settle at two, one, two"
assert settle_reaction_counts([{"N": 2}, {"H": 2}], [{"N": 1, "H": 3}]) == [
    1,
    3,
    2,
], "a multiplier of one is still reported"
assert settle_reaction_counts([{"Fe": 1}, {"O": 2}], [{"Fe": 2, "O": 3}]) == [
    4,
    3,
    2,
], "a two-letter symbol"
assert settle_reaction_counts(
    [{"C": 2, "H": 6}, {"O": 2}], [{"C": 1, "O": 2}, {"H": 2, "O": 1}]
) == [2, 7, 4, 6], "a multiplier past five is still in range"
assert (
    settle_reaction_counts([{"C": 1}, {"H": 2}], [{"C": 1, "H": 4}, {"O": 2}]) == []
), "a symbol only the right-hand side mentions blocks it"
assert settle_reaction_counts([{"H": 2, "O": 1}], [{"H": 2, "O": 2}]) == [], (
    "nothing in range settles it"
)
assert (
    settle_reaction_counts(
        [{"C": 4, "H": 10}, {"O": 2}], [{"C": 1, "O": 2}, {"H": 2, "O": 1}]
    )
    == []
), "the least answer runs past ten"
assert settle_reaction_counts([{"H": 2, "O": 1}], [{"H": 2, "O": 1}]) == [1, 1], (
    "already settled"
)

assert rejects({"H": 2}, [{"H": 2}]), "the left-hand side is not a list"
assert rejects([{"H": 2}], "H2"), "the right-hand side is not a list"
assert rejects([], [{"H": 2}]), "an empty side"
assert rejects([{"H": 2}], []), "the other side empty"
assert rejects(["H2"], [{"H": 2}]), "a species that is not a mapping"
assert rejects([{}], [{"H": 2}]), "a species mentioning nothing"
assert rejects([{"h": 2}], [{"h": 2}]), "a symbol with no capital"
assert rejects([{"HE": 2}], [{"HE": 2}]), "a symbol with two capitals"
assert rejects([{"H": 0}], [{"H": 1}]), "a holding of zero"
assert rejects([{"H": "2"}], [{"H": 2}]), "a holding that is not a number"
assert rejects(
    [{"H": 1}, {"C": 1}, {"N": 1}], [{"O": 1}, {"S": 1}, {"P": 1}]
), "more than five species"
print("ok")
