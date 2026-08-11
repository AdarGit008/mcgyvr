from solution import fill_order

assert fill_order([[5, 3]], 3) == {
    "cost": 15,
    "taken": [3],
    "leftover": [0],
}, "one source drained exactly"
assert fill_order([[5, 10]], 4) == {
    "cost": 20,
    "taken": [4],
    "leftover": [6],
}, "the draw stops at the need"
assert fill_order([[9, 5], [2, 3]], 4) == {
    "cost": 15,
    "taken": [1, 3],
    "leftover": [4, 0],
}, "the cheapest source drains first"
assert fill_order([[4, 2], [4, 5]], 3) == {
    "cost": 12,
    "taken": [2, 1],
    "leftover": [0, 4],
}, "a cost tie goes to the earlier source"
assert fill_order([[3, 2], [7, 2]], 4) == {
    "cost": 20,
    "taken": [2, 2],
    "leftover": [0, 0],
}, "the order may drain every source"
assert fill_order([[6, 2], [1, 2], [4, 2]], 5) == {
    "cost": 16,
    "taken": [1, 2, 2],
    "leftover": [1, 0, 0],
}, "three sources drain by rising price"
assert fill_order([[2, 9], [5, 1]], 6) == {
    "cost": 12,
    "taken": [6, 0],
    "leftover": [3, 1],
}, "an untouched source reads zero taken"
assert fill_order([[8, 1]], 1) == {
    "cost": 8,
    "taken": [1],
    "leftover": [0],
}, "a single unit order"


def rejects(sources, needed):
    try:
        fill_order(sources, needed)
    except Exception:
        return True
    return False


assert rejects([[2, 1]], 5), "stock cannot cover the order"
assert rejects([[2, 1]], 0), "zero needed is rejected"
assert rejects([[2, 1]], 2.5), "fractional needed is rejected"
assert rejects([[0, 4]], 1), "zero cost is rejected"
assert rejects([[2, -1]], 1), "negative stock is rejected"
assert rejects([[2]], 1), "a lone-element source is rejected"
print("ok")
