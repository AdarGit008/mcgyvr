from solution import compute_sheet

assert compute_sheet({"A1": "4", "B2": "-7"}) == {
    "A1": 4,
    "B2": -7,
}, "literal cells evaluate to their integers"
assert compute_sheet({"A1": "2", "B1": "=A1 + 3", "C1": "=B1+B1"}) == {
    "A1": 2,
    "B1": 5,
    "C1": 10,
}, "chained references resolve through intermediates"
assert compute_sheet({}) == {}, "empty sheet yields empty mapping"
assert compute_sheet({"Z9": "=5+-2"}) == {
    "Z9": 3
}, "a formula may hold only literals, including negatives"
assert compute_sheet({"A1": "=B1+C1", "B1": "=C1+1", "C1": "10"}) == {
    "A1": 21,
    "B1": 11,
    "C1": 10,
}, "key order must not matter to resolution"
assert compute_sheet({"AB12": "3", "C1": "=AB12+AB12+AB12"}) == {
    "AB12": 3,
    "C1": 9,
}, "multi-letter columns and repeated terms"


def rejects(sheet):
    try:
        compute_sheet(sheet)
    except ValueError:
        return True
    return False


assert rejects({"A1": "=B1"}), "unknown reference"
assert rejects({"A1": "=A1"}), "self reference"
assert rejects({"A1": "=B1", "B1": "=A1"}), "two-cell cycle"
assert rejects({"A1": "=1*2"}), "unsupported operator"
assert rejects({"A1": "hello"}), "malformed literal"
assert rejects({"A1": "="}), "empty formula"
print("ok")
