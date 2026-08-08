from solution import shelf_count

assert shelf_count([]) == [0, 0], "empty entry list"
assert shelf_count([["add", 5], ["take", 2]]) == [3, 0], "add then take within stock"
assert shelf_count([["add", 2], ["take", 5]]) == [
    2,
    1,
], "oversized take is skipped and tallied, count untouched"
assert shelf_count([["take", 1]]) == [0, 1], "taking from an empty shelf is skipped"
assert shelf_count([["add", 4], ["take", 4]]) == [
    0,
    0,
], "taking exactly the stock is applied"
assert shelf_count([["add", 9], ["fix", 3], ["take", 2]]) == [
    1,
    0,
], "fix overwrites the running count"
assert shelf_count([["take", 2], ["add", 1], ["take", 3], ["take", 1]]) == [
    0,
    2,
], "each skipped take is tallied"


def rejects(entries):
    try:
        shelf_count(entries)
    except ValueError:
        return True
    return False


assert rejects([["drop", 1]]), "unknown kind is rejected"
assert rejects([["add", -2]]), "negative amount is rejected"
assert rejects([["add", 1.5]]), "fractional amount is rejected"
assert rejects([["take", "3"]]), "non-numeric amount is rejected"
print("ok")
