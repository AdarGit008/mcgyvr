from solution import hand_out_chores

assert hand_out_chores(["mop", "dust", "sweep"], ["Ann", "Bo", "Cy"]) == {
    "Ann": ["mop", "dust"],
    "Bo": ["sweep"],
    "Cy": [],
}, "the step is the chore's own length"
assert hand_out_chores([], ["Ann", "Bo"]) == {
    "Ann": [],
    "Bo": [],
}, "an empty board still names the whole crew"
assert hand_out_chores(["a", "bb", "ccc"], ["Xu", "Yi"]) == {
    "Xu": ["a"],
    "Yi": ["bb", "ccc"],
}, "a step of two lands back on the same person"
assert hand_out_chores(["a", "b"], ["Solo"]) == {
    "Solo": ["a", "b"]
}, "a crew of one takes everything"
assert hand_out_chores(["longer", "x"], ["A", "B", "C", "D"]) == {
    "A": ["longer"],
    "B": [],
    "C": ["x"],
    "D": [],
}, "the marker wraps around the ring"
assert hand_out_chores(["ab", "cd", "ef"], ["P", "Q"]) == {
    "P": ["ab", "cd", "ef"],
    "Q": [],
}, "an even step can starve half the ring"


def rejects(chores, crew):
    try:
        hand_out_chores(chores, crew)
    except ValueError:
        return True
    return False


assert rejects("mop", ["Ann"]), "a board that is not a list is rejected"
assert rejects([""], ["Ann"]), "an empty chore is rejected"
assert rejects([9], ["Ann"]), "a non-string chore is rejected"
assert rejects(["mop", "mop"], ["Ann"]), "a chore listed twice is rejected"
assert rejects(["mop"], "Ann"), "a crew that is not a list is rejected"
assert rejects(["mop"], []), "an empty crew is rejected"
assert rejects(["mop"], [""]), "an empty crew name is rejected"
assert rejects(["mop"], [7]), "a non-string crew name is rejected"
assert rejects(["mop"], ["Ann", "Ann"]), "two crew members sharing a name is rejected"
print("ok")
