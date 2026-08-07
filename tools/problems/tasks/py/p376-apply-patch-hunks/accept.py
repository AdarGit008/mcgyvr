from solution import apply_patch_hunks

file = ["alpha", "beta", "gamma", "delta", "epsilon"]

assert apply_patch_hunks(file, []) == {
    "lines": ["alpha", "beta", "gamma", "delta", "epsilon"],
    "conflicts": [],
}, "no hunks leaves the file whole"
assert apply_patch_hunks(file, [{"at": 2, "before": ["beta"], "after": ["BETA"]}]) == {
    "lines": ["alpha", "BETA", "gamma", "delta", "epsilon"],
    "conflicts": [],
}, "one line swapped for another"
assert apply_patch_hunks(file, [{"at": 3, "before": [], "after": ["one", "two"]}]) == {
    "lines": ["alpha", "beta", "one", "two", "gamma", "delta", "epsilon"],
    "conflicts": [],
}, "an empty before drops the after lines ahead of the line at at"
assert apply_patch_hunks(file, [{"at": 6, "before": [], "after": ["zeta"]}]) == {
    "lines": ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"],
    "conflicts": [],
}, "an at one past the last line adds to the end"
assert apply_patch_hunks(file, [{"at": 2, "before": ["beta", "gamma"], "after": []}]) == {
    "lines": ["alpha", "delta", "epsilon"],
    "conflicts": [],
}, "an empty after takes the covered lines out"
assert apply_patch_hunks(
    file,
    [
        {"at": 1, "before": ["alpha"], "after": ["a-one", "a-two"]},
        {"at": 4, "before": ["delta"], "after": ["D"]},
    ],
) == {
    "lines": ["a-one", "a-two", "beta", "gamma", "D", "epsilon"],
    "conflicts": [],
}, "the second at is still measured against the file as handed in"
assert apply_patch_hunks(file, [{"at": 2, "before": ["wrong"], "after": ["x"]}]) == {
    "lines": ["alpha", "beta", "gamma", "delta", "epsilon"],
    "conflicts": [0],
}, "a before that does not match changes nothing"
assert apply_patch_hunks(
    file,
    [
        {"at": 2, "before": ["wrong"], "after": ["x"]},
        {"at": 4, "before": ["delta"], "after": ["D"]},
    ],
) == {
    "lines": ["alpha", "beta", "gamma", "D", "epsilon"],
    "conflicts": [0],
}, "a clashing hunk does not stop the ones behind it"
assert apply_patch_hunks(file, [{"at": 9, "before": ["zeta"], "after": ["y"]}]) == {
    "lines": ["alpha", "beta", "gamma", "delta", "epsilon"],
    "conflicts": [0],
}, "a reach running off the end conflicts"
assert apply_patch_hunks(file, [{"at": 5, "before": ["epsilon", "zeta"], "after": ["e"]}]) == {
    "lines": ["alpha", "beta", "gamma", "delta", "epsilon"],
    "conflicts": [0],
}, "a before longer than what remains conflicts"
assert apply_patch_hunks([], [{"at": 1, "before": [], "after": ["only"]}]) == {
    "lines": ["only"],
    "conflicts": [],
}, "an empty file may be written into at one"
assert apply_patch_hunks([], [{"at": 2, "before": [], "after": ["only"]}]) == {
    "lines": [],
    "conflicts": [0],
}, "an at two past an empty file conflicts"
assert apply_patch_hunks(
    file,
    [
        {"at": 1, "before": ["alpha"], "after": []},
        {"at": 3, "before": ["gamma"], "after": ["G1", "G2"]},
        {"at": 5, "before": ["nope"], "after": ["E"]},
    ],
) == {
    "lines": ["beta", "G1", "G2", "delta", "epsilon"],
    "conflicts": [2],
}, "three hunks, one of them clashing"


def rejects(given, hunks):
    try:
        apply_patch_hunks(given, hunks)
    except ValueError:
        return True
    return False


assert rejects(file, [{"at": 0, "before": [], "after": ["x"]}]), "an at below one is refused"
assert rejects(file, [{"at": 1.5, "before": [], "after": ["x"]}]), "a fractional at is refused"
assert rejects(
    file,
    [{"at": 3, "before": ["gamma"], "after": []}, {"at": 2, "before": ["beta"], "after": []}],
), "ats that do not climb are refused"
assert rejects(
    file,
    [{"at": 1, "before": ["alpha", "beta"], "after": []}, {"at": 2, "before": ["beta"], "after": []}],
), "a hunk reaching into the next is refused"
assert rejects(file, [{"at": 1, "before": "alpha", "after": []}]), "a before that is not a list is refused"
assert rejects(file, [{"at": 1, "before": [], "after": [7]}]), "an after holding a non-string is refused"
assert rejects(["a", 2], []), "a file holding a non-string is refused"
assert rejects(file, "hunks"), "hunks that are not a list are refused"
assert rejects(file, ["hunk"]), "a hunk that is not a mapping is refused"
print("ok")
