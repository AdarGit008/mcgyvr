from solution import fill_desk_map

assert fill_desk_map(
    ["aa.bb", "#a.b#", "..c.."], {"a": ["Ada", "Bo"], "b": ["Cyd"], "c": []}
) == {
    "floor": ["AB.Cb", "#a.b#", "..c.."],
    "sat": ["Ada r0 c0", "Bo r0 c1", "Cyd r0 c3"],
    "spare": 4,
}, "banks fill in reading order and leftovers stay small"
assert fill_desk_map(["dd", "dd"], {"d": ["Wu", "Xi", "Yo", "Ze"]}) == {
    "floor": ["WX", "YZ"],
    "sat": ["Wu r0 c0", "Xi r0 c1", "Yo r1 c0", "Ze r1 c1"],
    "spare": 0,
}, "a bank can be filled to the last desk"
assert fill_desk_map(["ab", "#."], {}) == {
    "floor": ["ab", "#."],
    "sat": [],
    "spare": 2,
}, "an empty legend leaves the floor as drawn"
assert fill_desk_map(["zaz"], {"z": ["Mo"], "a": ["Nia"]}) == {
    "floor": ["MNz"],
    "sat": ["Nia r0 c1", "Mo r0 c0"],
    "spare": 1,
}, "banks are reported in rising letter order"
assert fill_desk_map(["p", "p"], {"p": ["ann"]}) == {
    "floor": ["A", "p"],
    "sat": ["ann r0 c0"],
    "spare": 1,
}, "the opening letter is written as a capital"
assert fill_desk_map(["...", "###"], {})["spare"] == 0, "a floor with no desks has no spare desks"


def rejects(plan, legend):
    try:
        fill_desk_map(plan, legend)
    except ValueError:
        return True
    return False


assert rejects("aa", {}), "a floor that is not a list is rejected"
assert rejects([], {}), "an empty floor is rejected"
assert rejects([7], {}), "a row that is not a string is rejected"
assert rejects([""], {}), "an empty row is rejected"
assert rejects(["aa", "a"], {}), "ragged rows are rejected"
assert rejects(["aA"], {}), "a stray character is rejected"
assert rejects(["aa"], []), "a legend that is not a mapping is rejected"
assert rejects(["aa"], {"ab": []}), "a two letter bank key is rejected"
assert rejects(["aa"], {"b": []}), "a bank the floor never draws is rejected"
assert rejects(["aa"], {"a": "Ada"}), "a legend value that is not a list is rejected"
assert rejects(["aa"], {"a": ["A1"]}), "a name with a digit is rejected"
assert rejects(["aa"], {"a": [""]}), "an empty name is rejected"
assert rejects(["ab"], {"a": ["Ada"], "b": ["Ada"]}), "one name at two desks is rejected"
assert rejects(["a"], {"a": ["Ada", "Bo"]}), "more people than desks is rejected"
print("ok")
