from solution import shelf_count

assert shelf_count(5, []) == {"ending": 5, "peak": 5}, "empty ledger"
assert shelf_count(0, [["receive", 3], ["issue", 1]]) == {
    "ending": 2,
    "peak": 3,
}, "receive then issue"
assert shelf_count(4, [["issue", 1], ["issue", 3]]) == {
    "ending": 0,
    "peak": 4,
}, "peak is the starting count under issues alone"
assert shelf_count(2, [["receive", 5], ["issue", 6], ["receive", 1]]) == {
    "ending": 2,
    "peak": 7,
}, "peak sits mid-ledger"
assert shelf_count(3, [["issue", 3]]) == {
    "ending": 0,
    "peak": 3,
}, "an issue may empty the shelf exactly"


def rejects(*args):
    try:
        shelf_count(*args)
    except ValueError:
        return True
    return False


assert rejects(-1, []), "negative starting count is rejected"
assert rejects(1.5, []), "fractional starting count is rejected"
assert rejects(3, [["receive"]]), "one-item move is rejected"
assert rejects(3, [["receive", 0]]), "zero qty is rejected"
assert rejects(3, [["donate", 2]]), "unknown kind is rejected"
assert rejects(3, [["issue", 4]]), "overdraw is rejected"
print("ok")
