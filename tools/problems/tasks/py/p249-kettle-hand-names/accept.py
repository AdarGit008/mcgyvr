from solution import name_kettle_hands

assert name_kettle_hands([["g1", "h2", "j3", "k4"]]) == {
    "names": ["kiln-run"],
    "totals": [10],
}, "four running heats across four flues"
assert name_kettle_hands([["g1", "g5", "h2", "h8"]]) == {
    "names": ["double-flue"],
    "totals": [16],
}, "two flues covering two cards each"
assert name_kettle_hands([["g1", "h2", "j4", "g7"]]) == {
    "names": ["banked"],
    "totals": [14],
}, "heats adding to a multiple of seven"
assert name_kettle_hands([["g1", "h3", "j4", "k8"]]) == {
    "names": ["draught"],
    "totals": [16],
}, "a spread of six or more"
assert name_kettle_hands([["g1", "h2", "j3", "k6"]]) == {
    "names": ["cold"],
    "totals": [12],
}, "a hand no line fits"
assert name_kettle_hands([["g1", "h1", "j3", "k4"]]) == {
    "names": ["cold"],
    "totals": [9],
}, "a repeated heat is not a run"
assert name_kettle_hands([["g2", "h2", "j5", "k5"]]) == {
    "names": ["banked"],
    "totals": [14],
}, "two repeated heats three apart fall through to banked"
assert name_kettle_hands([["g1", "g2", "g3", "h4"]]) == {
    "names": ["cold"],
    "totals": [10],
}, "two flues split three and one are no double-flue"
assert name_kettle_hands(
    [
        ["g1", "h2", "j3", "k4"],
        ["g2", "h2", "j5", "k5"],
        ["g1", "h1", "j3", "k4"],
    ]
) == {
    "names": ["kiln-run", "banked", "cold"],
    "totals": [10, 14, 9],
}, "several hands keep the order they arrived in"


def rejects(value):
    try:
        name_kettle_hands(value)
    except ValueError:
        return True
    return False


assert rejects("hands"), "a non-list argument is rejected"
assert rejects([]), "an empty list of hands is rejected"
assert rejects([["g1", "h2", "j3"]]), "a hand of three cards is rejected"
assert rejects(["g1h2"]), "a hand that is not a list is rejected"
assert rejects([["g1", "h2", "j3", "k9"]]), "a heat of nine is rejected"
assert rejects([["g1", "h2", "j3", "z4"]]), "an unknown flue letter is rejected"
assert rejects([["g1", "g1", "h2", "j3"]]), "a card written twice is rejected"
assert rejects([["g1", "h2", "j3", 4]]), "a card that is not a string is rejected"
print("ok")
