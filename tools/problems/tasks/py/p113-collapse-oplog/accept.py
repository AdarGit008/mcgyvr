from solution import collapse_oplog

assert collapse_oplog([]) == [], "empty log stays empty"
assert collapse_oplog([["set", "a", 1]]) == [["set", "a", 1]], "single record kept"
assert collapse_oplog([["set", "a", 1], ["set", "a", 9]]) == [
    ["set", "a", 9]
], "the later set wins"
assert collapse_oplog([["set", "a", 1], ["drop", "a"]]) == [
    ["drop", "a"]
], "a drop after a set wins"
assert collapse_oplog([["drop", "a"], ["set", "a", 3]]) == [
    ["set", "a", 3]
], "a set after a drop wins"
assert collapse_oplog([["set", "b", 2], ["set", "a", 1]]) == [
    ["set", "a", 1],
    ["set", "b", 2],
], "output is sorted by key"
assert collapse_oplog(
    [
        ["set", "b", 1],
        ["drop", "c"],
        ["set", "b", 4],
        ["set", "c", 8],
        ["drop", "b"],
    ]
) == [["drop", "b"], ["set", "c", 8]], "mixed keys each keep their final record"


def rejects(log):
    try:
        collapse_oplog(log)
    except ValueError:
        return True
    return False


assert rejects([["swap", "a", 1]]), "unknown kind"
assert rejects([["set", 7, 1]]), "non-string key"
assert rejects([["set", "a", "x"]]), "non-integer value"
print("ok")
