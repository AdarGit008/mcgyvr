from solution import kinship_degree

REGISTER = {
    "amos": [],
    "olive": ["amos"],
    "pearl": ["amos"],
    "rex": ["olive", "pearl"],
    "sara": ["olive", "pearl"],
    "tom": ["rex"],
    "una": ["sara"],
    "vic": ["tom"],
    "wren": ["una"],
    "yuri": [],
    "zoe": ["yuri"],
}


def rejects(register, one, other):
    try:
        kinship_degree(register, one, other)
    except ValueError:
        return True
    return False


assert kinship_degree(REGISTER, "rex", "rex") == {
    "steps": 0,
    "line": "direct",
    "meet": "rex",
}, "a person against themselves stands nought steps away"

assert kinship_degree(REGISTER, "rex", "olive") == {
    "steps": 1,
    "line": "direct",
    "meet": "olive",
}, "one step up the direct line"

assert kinship_degree(REGISTER, "olive", "rex") == {
    "steps": 1,
    "line": "direct",
    "meet": "olive",
}, "the elder is the meeting point whichever way round the two are given"

assert kinship_degree(REGISTER, "vic", "amos") == {
    "steps": 4,
    "line": "direct",
    "meet": "amos",
}, "four steps up the direct line"

assert kinship_degree(REGISTER, "amos", "vic") == {
    "steps": 4,
    "line": "direct",
    "meet": "amos",
}, "and the same four counted downward"

assert kinship_degree(REGISTER, "rex", "sara") == {
    "steps": 2,
    "line": "collateral",
    "meet": "olive",
}, "two shared forebears at the same sum, and the name that sorts first takes it"

assert kinship_degree(REGISTER, "tom", "una") == {
    "steps": 4,
    "line": "collateral",
    "meet": "olive",
}, "the nearer shared forebear beats the one further up"

assert kinship_degree(REGISTER, "tom", "sara") == {
    "steps": 3,
    "line": "collateral",
    "meet": "olive",
}, "an uneven pair of climbs still adds to the least sum"

assert kinship_degree(REGISTER, "wren", "vic") == {
    "steps": 6,
    "line": "collateral",
    "meet": "olive",
}, "the longest collateral reach in the register"

assert kinship_degree(REGISTER, "rex", "zoe") == {
    "steps": 0,
    "line": "apart",
    "meet": "",
}, "two people out of each other's reach entirely"

assert kinship_degree(REGISTER, "zoe", "yuri") == {
    "steps": 1,
    "line": "direct",
    "meet": "yuri",
}, "the far branch has a direct line of its own"

assert rejects([], "a", "b"), "a register that is not a mapping is rejected"
assert rejects({"": []}, "", ""), "an empty key is rejected"
assert rejects({"a": "b", "b": []}, "a", "b"), "a forebear list that is not a list is rejected"
assert rejects(
    {"a": ["b", "c", "d"], "b": [], "c": [], "d": []}, "a", "b"
), "a third forebear is rejected"
assert rejects({"a": ["b", "b"], "b": []}, "a", "b"), "a forebear named twice is rejected"
assert rejects({"a": ["a"]}, "a", "a"), "someone made their own forebear is rejected"
assert rejects({"a": ["b"]}, "a", "a"), "a forebear who is not a key is rejected"
assert rejects({"a": [5], "b": []}, "a", "b"), "a forebear that is not a string is rejected"
assert rejects({"a": ["b"], "b": ["a"]}, "a", "b"), "a register that closes a loop is rejected"
assert rejects(REGISTER, "nobody", "rex"), "a second person who is not a key is rejected"
assert rejects(REGISTER, "rex", "nobody"), "a third person who is not a key is rejected"
assert rejects(REGISTER, 4, "rex"), "a person who is not a string is rejected"

print("ok")
