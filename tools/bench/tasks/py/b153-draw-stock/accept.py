from solution import draw_stock

assert draw_stock({"bolt": 4}, [["bolt", 3]]) == {"bolt": 1}, "one line pulls its count"
assert draw_stock({"bolt": 4}, [["bolt", 2], ["bolt", 2]]) == {"bolt": 0}, "repeat lines drain to zero, item kept"
assert draw_stock({"bolt": 4, "nut": 2}, [["bolt", 1]]) == {"bolt": 3, "nut": 2}, "untouched items keep their counts"
assert draw_stock({"nut": 0}, []) == {"nut": 0}, "an empty order changes nothing"
pantry = {"bolt": 5}
draw_stock(pantry, [["bolt", 5]])
assert pantry == {"bolt": 5}, "the shelf passed in is never modified"


def rejects(shelf, order):
    try:
        draw_stock(shelf, order)
    except Exception:
        return True
    return False


assert rejects({"bolt": -1}, []), "a negative shelf count is rejected"
assert rejects({"bolt": 1.5}, []), "a fractional shelf count is rejected"
assert rejects({"bolt": 4}, "bolt"), "a non-list order is rejected"
assert rejects({"bolt": 4}, [["washer", 1]]), "an item the shelf lacks is rejected"
assert rejects({"bolt": 4}, [["bolt", 0]]), "a zero line count is rejected"
assert rejects({"bolt": 4}, [["bolt", 3], ["bolt", 2]]), "pulling past the remainder is rejected"
print("ok")
