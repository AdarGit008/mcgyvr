from solution import process_stock_moves

assert process_stock_moves([]) == {"levels": {}, "refused": []}, "empty input"
assert process_stock_moves(
    [
        {"op": "receive", "item": "bolt", "qty": 5},
        {"op": "issue", "item": "bolt", "qty": 2},
    ]
) == {"levels": {"bolt": 3}, "refused": []}, "receive then issue"
assert process_stock_moves([{"op": "issue", "item": "nut", "qty": 1}]) == {
    "levels": {},
    "refused": [[0, "unknown_item"]],
}, "issuing an unseen item is refused and creates nothing"
assert process_stock_moves(
    [
        {"op": "receive", "item": "cog", "qty": 2},
        {"op": "issue", "item": "cog", "qty": 5},
        {"op": "issue", "item": "cog", "qty": 2},
    ]
) == {
    "levels": {"cog": 0},
    "refused": [[1, "short"]],
}, "a short issue is skipped, later moves still apply"
assert process_stock_moves(
    [
        {"op": "recount", "item": "pin", "qty": 0},
        {"op": "receive", "item": "pin", "qty": 4},
        {"op": "recount", "item": "pin", "qty": 1},
    ]
) == {"levels": {"pin": 1}, "refused": []}, "recount creates and overwrites"
assert process_stock_moves(
    [
        {"op": "receive", "item": "rod", "qty": 1},
        {"op": "issue", "item": "wire", "qty": 1},
        {"op": "issue", "item": "rod", "qty": 3},
        {"op": "issue", "item": "rod", "qty": 1},
    ]
) == {
    "levels": {"rod": 0},
    "refused": [[1, "unknown_item"], [2, "short"]],
}, "refusal indices and order, zero level still listed"


def rejects(moves):
    try:
        process_stock_moves(moves)
    except ValueError:
        return True
    return False


assert rejects([{"op": "ship", "item": "a", "qty": 1}]), "unknown op is rejected"
assert rejects([{"op": "receive", "item": "", "qty": 1}]), "empty item is rejected"
assert rejects(
    [{"op": "receive", "item": "a", "qty": "3"}]
), "non-integer qty is rejected"
assert rejects(
    [{"op": "issue", "item": "a", "qty": 0}]
), "issue qty below 1 is rejected"
assert rejects(
    [{"op": "recount", "item": "a", "qty": -1}]
), "recount below 0 is rejected"
assert rejects(
    [{"op": "receive", "item": "a", "qty": 1.5}]
), "fractional qty is rejected"
print("ok")
