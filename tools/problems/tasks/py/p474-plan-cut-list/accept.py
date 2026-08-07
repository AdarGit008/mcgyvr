from solution import plan_cut_list

assert plan_cut_list(
    [100, 100], [{"length": 40, "count": 3}, {"length": 30, "count": 2}], 3, 10
) == {
    "layout": [[40, 40], [40, 30]],
    "offcuts": [14, 24],
    "scrap": 0,
    "short": [30],
}, "a rack of two bars runs out one piece short"

assert plan_cut_list([10], [{"length": 5, "count": 2}], 0, 1) == {
    "layout": [[5, 5]],
    "offcuts": [],
    "scrap": 0,
    "short": [],
}, "a bar cut clean to its end leaves neither offcut nor scrap"

assert plan_cut_list([10], [{"length": 9, "count": 1}], 4, 1) == {
    "layout": [[9]],
    "offcuts": [],
    "scrap": 0,
    "short": [],
}, "a kerf wider than the tail leaves nothing at all"

assert plan_cut_list([20], [{"length": 8, "count": 2}], 1, 5) == {
    "layout": [[8, 8]],
    "offcuts": [],
    "scrap": 2,
    "short": [],
}, "a remainder under the keep length is scrap"

assert plan_cut_list([50, 30], [{"length": 20, "count": 1}], 2, 10) == {
    "layout": [[20], []],
    "offcuts": [28, 30],
    "scrap": 0,
    "short": [],
}, "an untouched bar goes back on the rack whole"

assert plan_cut_list(
    [10, 10],
    [{"length": 3, "count": 1}, {"length": 7, "count": 1}, {"length": 6, "count": 1}],
    0,
    2,
) == {
    "layout": [[7, 3], [6]],
    "offcuts": [4],
    "scrap": 0,
    "short": [],
}, "the longest piece is placed before the shortest whatever the order says"

assert plan_cut_list(
    [10], [{"length": 11, "count": 1}, {"length": 12, "count": 1}], 0, 1
) == {
    "layout": [[]],
    "offcuts": [10],
    "scrap": 0,
    "short": [12, 11],
}, "pieces longer than every bar are reported longest first"

assert plan_cut_list([], [{"length": 3, "count": 1}], 1, 1) == {
    "layout": [],
    "offcuts": [],
    "scrap": 0,
    "short": [3],
}, "an empty rack cuts nothing"

assert plan_cut_list([12], [], 1, 5) == {
    "layout": [[]],
    "offcuts": [12],
    "scrap": 0,
    "short": [],
}, "an empty order leaves the rack as it was"


def rejects(bars, orders, kerf, keep):
    try:
        plan_cut_list(bars, orders, kerf, keep)
    except ValueError:
        return True
    return False


assert rejects("100", [], 1, 1), "a bars argument that is not a list is rejected"
assert rejects([0], [], 1, 1), "a bar below one is rejected"
assert rejects([10], "none", 1, 1), "an orders argument that is not a list is rejected"
assert rejects([10], [[3, 1]], 1, 1), "an order that is not a mapping is rejected"
assert rejects([10], [{"length": 3}], 1, 1), "an order missing its count is rejected"
assert rejects(
    [10], [{"length": 3, "count": 1, "grade": "a"}], 1, 1
), "an order carrying a spare key is rejected"
assert rejects([10], [{"length": 0, "count": 1}], 1, 1), "a length below one is rejected"
assert rejects(
    [10], [{"length": 3, "count": 1}, {"length": 3, "count": 2}], 1, 1
), "a length named twice is rejected"
assert rejects([10], [{"length": 3, "count": 0}], 1, 1), "a count below one is rejected"
assert rejects([10], [], -1, 1), "a kerf below nought is rejected"
assert rejects([10], [], 1, -2), "a keep below nought is rejected"
assert rejects([10], [], 1.5, 1), "a kerf that is not whole is rejected"
print("ok")
