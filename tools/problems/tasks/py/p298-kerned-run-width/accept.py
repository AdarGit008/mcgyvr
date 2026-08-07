from solution import kerned_run_width

face = {"A": 7, "V": 7, "W": 9, "a": 5, "i": 1, "j": 0, ".": 3, " ": 4}


def rejects(text, widths, kerns, tracking):
    try:
        kerned_run_width(text, widths, kerns, tracking)
    except ValueError:
        return True
    return False


assert kerned_run_width("", face, [], 4) == 0, "an empty run measures zero"
assert kerned_run_width("A", face, [["AV", -3]], 3) == 7, (
    "one character takes no tracking"
)
assert kerned_run_width("AA", face, [], 1) == 15, "one couple takes one tracking"
assert kerned_run_width("AVa", face, [["AV", -3], ["Va", -1], ["AV", -99]], 1) == 17, (
    "both couples draw from the table and the lower AV row is dead weight"
)
assert kerned_run_width("AV", face, [["AV", -3], ["AV", 5]], 0) == 11, (
    "the higher row of a repeated couple is the one that counts"
)
assert kerned_run_width("Va", face, [["AV", -3]], 0) == 12, (
    "a table row for another couple grants nothing"
)
assert kerned_run_width("A V", face, [], 2) == 22, (
    "a space advances and carries tracking on both sides"
)
assert kerned_run_width("AAA", face, [], -2) == 17, "tracking may pull the run in"
assert kerned_run_width("jj", face, [], 0) == 0, "a zero advance is allowed"
assert kerned_run_width("WAV.", face, [["AV", -4], ["V.", -6]], 0) == 16, (
    "four characters and two granted couples"
)

assert rejects(5, face, [], 0), "a run is a string"
assert rejects("A", [], [], 0), "widths is a mapping"
assert rejects("Z", face, [], 0), "Z has no width"
assert rejects("A", {"A": 1.5}, [], 0), "a width is whole"
assert rejects("A", {"A": -1}, [], 0), "a width is not negative"
assert rejects("A", face, "none", 0), "kerns is a list"
assert rejects("AV", face, [["A", -1]], 0), "a couple is two characters"
assert rejects("AV", face, [["AV", 0.5]], 0), "a kern is whole"
assert rejects("AV", face, [], 1.5), "tracking is whole"
assert rejects("ii", {"i": 1}, [["ii", -5]], 0), "a run may not measure below zero"
print("ok")
