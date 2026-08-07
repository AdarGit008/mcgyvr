from solution import audit_unit_run

assert audit_unit_run(5, 6, [2, 3]) == {
    "verdict": "exact",
    "gap": [0, 1],
}, "a claim the pieces land on exactly"
assert audit_unit_run(3, 7, [3, 11, 231]) == {
    "verdict": "exact",
    "gap": [0, 1],
}, "three pieces landing on three sevenths"
assert audit_unit_run(7, 10, [2, 5]) == {
    "verdict": "exact",
    "gap": [0, 1],
}, "two pieces landing on seven tenths"
assert audit_unit_run(1, 2, [3]) == {
    "verdict": "short",
    "gap": [1, 6],
}, "one piece falling beneath the claim"
assert audit_unit_run(1, 3, [2]) == {
    "verdict": "over",
    "gap": [-1, 6],
}, "one piece overshooting the claim, minus sign on the top"
assert audit_unit_run(0, 5, []) == {
    "verdict": "exact",
    "gap": [0, 1],
}, "nothing claimed and nothing offered"
assert audit_unit_run(0, 5, [2]) == {
    "verdict": "over",
    "gap": [-1, 2],
}, "a piece offered against a claim of nothing"
assert audit_unit_run(1, 2, []) == {
    "verdict": "short",
    "gap": [1, 2],
}, "an empty run judged against a real claim"
assert audit_unit_run(1, 1, [2, 3, 6]) == {
    "verdict": "exact",
    "gap": [0, 1],
}, "a claim of one, met exactly"
assert audit_unit_run(2, 1, [2, 3, 6]) == {
    "verdict": "short",
    "gap": [1, 1],
}, "a claim above one leaves a whole gap"
assert audit_unit_run(2, 4, [2]) == {
    "verdict": "exact",
    "gap": [0, 1],
}, "a claim written unreduced is judged on its value"


def rejects(top, bottom, parts):
    try:
        audit_unit_run(top, bottom, parts)
    except ValueError:
        return True
    return False


assert rejects(1, 2, [99989, 99991]), "a running total past the ceiling is rejected"
assert rejects(1, 2, [1]), "a piece below two is rejected"
assert rejects(1, 2, [3, 3]), "a repeated piece is rejected"
assert rejects(1, 2, [3, 2]), "pieces out of order are rejected"
assert rejects(1, 2, [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]), "eleven pieces is rejected"
assert rejects(1, 2, [100001]), "a piece past the ceiling is rejected"
assert rejects(1, 2, [2.5]), "a fractional piece is rejected"
assert rejects(1, 2, "23"), "a run that is not a list is rejected"
assert rejects(-1, 2, []), "a negative top is rejected"
assert rejects(1, 0, []), "a bottom of nothing is rejected"
assert rejects(1, 100001, []), "a bottom past the ceiling is rejected"
print("ok")
