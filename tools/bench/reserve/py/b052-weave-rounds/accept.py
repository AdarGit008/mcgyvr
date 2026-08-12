from solution import weave_rounds, widest_list

assert weave_rounds([[1, 2, 3], [4, 5], [6]]) == [
    1,
    4,
    6,
    2,
    5,
    3,
], "three uneven lanes weave round by round"
assert weave_rounds([["a"], ["b", "c", "d"]]) == [
    "a",
    "b",
    "c",
    "d",
], "a short first lane drops out of later rounds"
assert weave_rounds([]) == [], "no lanes weave into an empty list"
assert weave_rounds([[], []]) == [], "all-empty lanes weave into an empty list"
assert weave_rounds([[7, 8, 9]]) == [7, 8, 9], "a single lane is copied"
assert widest_list([[1], [2, 3], []]) == 2, "widest_list finds the longest lane"
assert widest_list([]) == 0, "widest_list of no lanes is zero"


def rejects(value):
    try:
        weave_rounds(value)
    except Exception:
        return True
    return False


assert rejects("lanes"), "non-list argument is rejected"
assert rejects([[1], "x"]), "a non-list lane is rejected"
print("ok")
