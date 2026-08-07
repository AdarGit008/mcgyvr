from solution import keyset_page

assert keyset_page([1, 3, 5, 7, 9], 0, 2) == {
    "items": [1, 3],
    "done": False,
}, "first page"
assert keyset_page([1, 3, 5, 7, 9], 3, 2) == {
    "items": [5, 7],
    "done": False,
}, "middle page from a present cursor"
assert keyset_page([1, 3, 5, 7, 9], 7, 2) == {
    "items": [9],
    "done": True,
}, "short final page"
assert keyset_page([1, 3, 5, 7, 9], 9, 2) == {
    "items": [],
    "done": True,
}, "cursor at the end"
assert keyset_page([1, 3, 5], 4, 10) == {
    "items": [5],
    "done": True,
}, "cursor between ids"
assert keyset_page([2, 4, 6], 3, 1) == {
    "items": [4],
    "done": False,
}, "limit exactly consumed with more beyond"
assert keyset_page([], 5, 3) == {"items": [], "done": True}, "empty ids"


def rejects(*args):
    try:
        keyset_page(*args)
    except ValueError:
        return True
    return False


assert rejects([1, 2], 0, 0), "zero limit is rejected"
assert rejects([1, 2], 1.5, 1), "fractional cursor is rejected"
assert rejects([1, 2, 2], 0, 1), "repeated id is rejected"
assert rejects([3, 1], 0, 1), "descending ids are rejected"
print("ok")
