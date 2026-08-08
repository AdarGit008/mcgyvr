from solution import admit_bytes

assert admit_bytes(10, 20, 5, []) == [], "no entries, no labels"
assert admit_bytes(10, 20, 5, [[0, "a", 6], [1, "a", 6]]) == [
    "pass",
    "drop",
], "the per-key ceiling sheds the second burst"
assert admit_bytes(10, 12, 5, [[0, "a", 8], [0, "b", 8], [0, "c", 4]]) == [
    "pass",
    "drop",
    "pass",
], "the shared ceiling binds even when each key is fine"
assert admit_bytes(10, 20, 5, [[0, "a", 8], [1, "a", 5], [2, "a", 2]]) == [
    "pass",
    "drop",
    "pass",
], "a shed entry consumes nothing, so a smaller one squeezes in"
assert admit_bytes(10, 20, 5, [[0, "a", 10], [4, "a", 1], [5, "a", 10]]) == [
    "pass",
    "drop",
    "pass",
], "an entry ages out at exactly span"
assert admit_bytes(
    6, 20, 3, [[0, "a", 6], [1, "b", 6], [2, "b", 1], [3, "a", 6]]
) == ["pass", "pass", "drop", "pass"], "keys are metered independently"
assert admit_bytes(5, 20, 4, [[0, "a", 9]]) == [
    "drop"
], "an oversized entry is shed, not an error"


def rejects(*args):
    try:
        admit_bytes(*args)
    except ValueError:
        return True
    return False


assert rejects(0, 20, 5, []), "zero per_key"
assert rejects(10, 20, 0, []), "zero span"
assert rejects(10, 20, 5, [[0, "a", 0]]), "zero size"
assert rejects(10, 20, 5, [[-1, "a", 1]]), "negative time"
assert rejects(10, 20, 5, [[3, "a", 1], [2, "a", 1]]), "times running backwards"
assert rejects(10, 20, 5, [[0, "", 1]]), "empty key"
print("ok")
